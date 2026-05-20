-- =============================================================
-- ФАЙЛ: pioneer_mission.lua
-- НАЗНАЧЕНИЕ: взлет, поиск метки от OpenMV, наведение, посадка
--
-- В этом варианте объединены:
--   - основная логика миссии;
--   - более живучие LED-вызовы из проверочного скрипта;
--   - безопасное открытие UART после взлета.
--
-- OpenMV должна отправлять:
--   FOUND,cx,cy,size
--   NONE
-- =============================================================

-- ==================== ПАРАМЕТРЫ ====================
local TAKEOFF_HEIGHT    = 1.2
local SEARCH_HEIGHT     = 1.2
local APPROACH_HEIGHT   = 0.8
local PIXEL_TO_METER    = 0.002
local DEAD_ZONE_PX      = 30
local SIZE_CLOSE        = 130
local BLINK_INTERVAL    = 0.4
local MISSION_TIMEOUT   = 1100
local UART_ID           = 3
local UART_BAUD         = 115200

-- ==================== СОСТОЯНИЯ ====================
local STATE = {
    SEARCH   = "SEARCH",
    APPROACH = "APPROACH",
    DONE     = "DONE",
}

local current_state = STATE.SEARCH
local mission_start = os.clock()
local log_entries = {}
local uart = nil
local blink_state = false
local last_blink_time = 0
local blue_locked = false

-- ==================== ОБЩИЕ УТИЛИТЫ ====================
local function say(message)
    print("[MISSION] " .. tostring(message))
end

local function log(event, data)
    local t = string.format("%.2f", os.clock() - mission_start)
    local msg = string.format("[%ss] %s | %s", t, event, data or "")
    table.insert(log_entries, msg)
    say(msg)
end

local function safe_sleep(ms)
    if timer and timer.sleep then
        timer.sleep(ms)
        return
    end

    local finish = os.clock() + (ms / 1000.0)
    while os.clock() < finish do
    end
end

local function try_call(name, fn)
    local ok, result = pcall(fn)
    if not ok then
        log(name .. "_ERROR", tostring(result))
        return false, nil
    end
    return true, result
end

local function save_log()
    local ok, err = pcall(function()
        local f = io.open("mission_log.txt", "w")
        if f then
            f:write("=== MISSION LOG ===\n")
            f:write("Start: " .. tostring(os.date()) .. "\n")
            f:write("===================\n")
            for _, line in ipairs(log_entries) do
                f:write(line .. "\n")
            end
            f:write("=== END ===\n")
            f:close()
        end
    end)

    if not ok then
        say("log save failed: " .. tostring(err))
    end
end

-- ==================== LED ====================
local function set_led(r, g, b)
    -- LED не должен валить миссию: пробуем несколько вариантов API.
    local ok = try_call("pioneer.setLedsColor", function()
        pioneer.setLedsColor(r, g, b)
    end)
    if ok then
        return true
    end

    ok = try_call("pioneer.setLedColor", function()
        pioneer.setLedColor(r, g, b)
    end)
    if ok then
        return true
    end

    ok = try_call("pioneer.led_control", function()
        pioneer.led_control(r, g, b)
    end)
    if ok then
        return true
    end

    return false
end

local function led_red()
    if not blue_locked then
        set_led(255, 0, 0)
    end
end

local function led_blue()
    blue_locked = true
    set_led(0, 0, 255)
end

local function led_off()
    if not blue_locked then
        set_led(0, 0, 0)
    end
end

local function led_green_blink_tick()
    if blue_locked then
        return
    end

    local now = os.clock()
    if (now - last_blink_time) >= BLINK_INTERVAL then
        blink_state = not blink_state
        if blink_state then
            set_led(0, 255, 0)
        else
            set_led(0, 0, 0)
        end
        last_blink_time = now
    end
end

-- ==================== УПРАВЛЕНИЕ ДРОНОМ ====================
local function arm()
    local ok = try_call("pioneer.arm", function()
        pioneer.arm()
    end)
    if ok then
        return true
    end

    ok = try_call("pioneer.arming", function()
        pioneer.arming()
    end)
    if ok then
        return true
    end

    return false
end

local function takeoff(height)
    local ok = false

    ok = try_call("pioneer.takeoff_height", function()
        pioneer.takeoff(height)
    end) or ok

    if not ok then
        ok = try_call("pioneer.takeoff", function()
            pioneer.takeoff()
        end) or ok
    end

    return ok
end

local function set_target_point(x, y, z, yaw)
    return try_call("pioneer.setTargetPoint", function()
        pioneer.setTargetPoint(x, y, z, yaw or 0)
    end)
end

local function set_velocity(vx, vy, vz, vyaw)
    return try_call("pioneer.setVelocity", function()
        pioneer.setVelocity(vx, vy, vz, vyaw or 0)
    end)
end

local function land()
    return try_call("pioneer.land", function()
        pioneer.land()
    end)
end

local function disarm()
    return try_call("pioneer.disarm", function()
        pioneer.disarm()
    end)
end

-- ==================== UART / OPENMV ====================
local function init_uart()
    if uart then
        return true
    end

    local ok, result = try_call("serial.open", function()
        return serial.open(UART_ID, UART_BAUD)
    end)

    if ok and result then
        uart = result
        log("UART", "opened UART" .. tostring(UART_ID) .. " baud=" .. tostring(UART_BAUD))
        return true
    end

    return false
end

local function read_marker()
    if not uart then
        return { found = false }
    end

    local ok, line = try_call("uart.readline", function()
        return uart:readline()
    end)

    if not ok or not line then
        return { found = false }
    end

    line = line:gsub("[\r\n]", "")
    if line == "" or line == "NONE" then
        return { found = false }
    end

    local prefix, cx, cy, size = line:match("(%u+),(-?%d+),(-?%d+),(%d+)")
    if prefix == "FOUND" then
        return {
            found = true,
            cx = tonumber(cx),
            cy = tonumber(cy),
            size = tonumber(size),
        }
    end

    return { found = false }
end

-- ==================== МИССИЯ ====================
log("MISSION_START", "script started")

-- 1. Взлет: красный LED, ARM, TAKEOFF.
led_red()
log("LED", "red")

arm()
safe_sleep(700)

local takeoff_ok = takeoff(TAKEOFF_HEIGHT)
if takeoff_ok then
    log("TAKEOFF", "command sent, height=" .. tostring(TAKEOFF_HEIGHT))
else
    log("TAKEOFF", "command failed, continuing for diagnostics")
end

safe_sleep(5000)

-- UART после взлета: если порт не откроется, дрон просто будет искать/зависать.
init_uart()

-- 2. Поиск: зеленое мигание, удержание точки поиска.
log("STATE", "SEARCH")
set_target_point(0, 0, SEARCH_HEIGHT, 0)

while current_state ~= STATE.DONE do
    if (os.clock() - mission_start) > MISSION_TIMEOUT then
        log("TIMEOUT", "landing")
        led_off()
        land()
        safe_sleep(4000)
        disarm()
        save_log()
        return
    end

    if not uart then
        init_uart()
    end

    local marker = read_marker()

    if current_state == STATE.SEARCH then
        led_green_blink_tick()

        if marker.found then
            log("MARKER_FOUND", string.format("cx=%d cy=%d size=%d", marker.cx, marker.cy, marker.size))
            led_blue()
            current_state = STATE.APPROACH
        end

    elseif current_state == STATE.APPROACH then
        if marker.found then
            local centered = math.abs(marker.cx) < DEAD_ZONE_PX and math.abs(marker.cy) < DEAD_ZONE_PX
            local close_enough = marker.size >= SIZE_CLOSE

            -- OpenMV: cx > 0 значит метка правее центра кадра.
            -- Знаки могут потребовать инверсии после реального теста.
            local dx = marker.cx * PIXEL_TO_METER
            local dy = marker.cy * PIXEL_TO_METER

            log("APPROACH", string.format("cx=%d cy=%d size=%d dx=%.3f dy=%.3f", marker.cx, marker.cy, marker.size, dx, dy))

            if centered and close_enough then
                log("LANDING_START", "centered and close")
                led_blue()
                land()
                safe_sleep(5000)
                disarm()
                current_state = STATE.DONE

            elseif centered then
                set_target_point(0, 0, APPROACH_HEIGHT, 0)

            else
                set_velocity(dy, dx, 0, 0)
            end
        else
            log("MARKER_LOST", "hover/search")
            set_velocity(0, 0, 0, 0)
            current_state = STATE.SEARCH
            blue_locked = false
        end
    end

    safe_sleep(100)
end

led_blue()
log("MISSION_COMPLETE", "done")
save_log()
