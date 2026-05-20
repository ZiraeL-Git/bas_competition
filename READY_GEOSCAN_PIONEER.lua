-- =============================================================
-- READY_GEOSCAN_PIONEER.lua
-- Живучий бортовой скрипт для Geoscan Pioneer.
--
-- Что делает:
--   1. СРАЗУ включает красный LED, чтобы было видно, что файл стартовал.
--   2. Командует предполетную подготовку и взлет через официальный ap API.
--   3. Читает OpenMV по UART4 9600.
--   4. Ищет метку, наводится через ap.goToLocalPoint(), садится.
--
-- OpenMV -> Pioneer, UART4 9600:
--   0xAA, status, cx, cy, size
--   status = 1: метка найдена
--   status = 0: метка не найдена
--   cx, cy = координаты центра в кадре 160x120
--   size = примерный размер метки в пикселях
-- =============================================================

local unpack_fn = table.unpack or unpack

-- ==================== ПАРАМЕТРЫ ====================
local LED_COUNT = 4
local UART_NUM = 4
local UART_BAUD = 9600

local FRAME_CX = 80
local FRAME_CY = 60

local SEARCH_HEIGHT = 1.2
local APPROACH_HEIGHT = 0.7

local DEAD_ZONE_PX = 12
local LAND_SIZE_PX = 70
local PIXEL_TO_METER = 0.003
local MAX_STEP_M = 0.18

local LOOP_PERIOD = 0.1
local MARKER_TIMEOUT = 0.8
local TAKEOFF_DELAY = 2.0
local SEARCH_DELAY = 7.0
local MISSION_TIMEOUT = 180

-- ==================== БАЗОВЫЕ УТИЛИТЫ ====================
local function now()
    if time then
        return time()
    end
    if os and os.clock then
        return os.clock()
    end
    return 0
end

local function log(message)
    pcall(function()
        print("[READY] " .. tostring(message))
    end)
end

local function safe_call(name, fn)
    local ok, err = pcall(fn)
    if not ok then
        log(name .. " ERROR: " .. tostring(err))
        return false
    end
    return true
end

local function clamp(v, lo, hi)
    if v < lo then
        return lo
    end
    if v > hi then
        return hi
    end
    return v
end

-- ==================== LED: ПЕРВЫЙ ПРИЗНАК ЖИЗНИ ====================
local leds = Ledbar.new(LED_COUNT)

local function change_color(col)
    for i = 0, LED_COUNT - 1, 1 do
        leds:set(i, unpack_fn(col))
    end
end

local function led_red()
    change_color({1, 0, 0})
end

local function led_green()
    change_color({0, 1, 0})
end

local function led_blue()
    change_color({0, 0, 1})
end

local function led_yellow()
    change_color({1, 1, 0})
end

local function led_off()
    change_color({0, 0, 0})
end

led_red()
log("script loaded")

-- ==================== СОСТОЯНИЕ ====================
local STATE_BOOT = "BOOT"
local STATE_TAKEOFF = "TAKEOFF"
local STATE_SEARCH = "SEARCH"
local STATE_APPROACH = "APPROACH"
local STATE_LANDING = "LANDING"
local STATE_DONE = "DONE"

local state = STATE_BOOT
local start_time = now()
local last_marker_time = -1000
local last_blink_time = 0
local blink_on = false
local uart = nil
local rx_buffer = ""
local target_x = 0
local target_y = 0
local target_z = SEARCH_HEIGHT

local latest_marker = {
    found = false,
    cx = FRAME_CX,
    cy = FRAME_CY,
    size = 0,
}

-- ==================== UART ====================
local function init_uart()
    if uart then
        return true
    end

    local ok, result = pcall(function()
        return Uart.new(UART_NUM, UART_BAUD, Uart.PARITY_NONE, 1)
    end)

    if ok and result then
        uart = result
        log("uart opened")
        return true
    end

    log("uart not opened")
    return false
end

local function parse_uart()
    if not uart then
        init_uart()
        return
    end

    local ok, bytes = pcall(function()
        return uart:bytesToRead()
    end)

    if not ok or not bytes or bytes <= 0 then
        return
    end

    local ok_read, data = pcall(function()
        return uart:read(bytes)
    end)

    if not ok_read or not data then
        return
    end

    rx_buffer = rx_buffer .. data

    while #rx_buffer >= 5 do
        local header = string.byte(rx_buffer, 1)
        if header ~= 170 then
            rx_buffer = string.sub(rx_buffer, 2)
        else
            local status = string.byte(rx_buffer, 2)
            local cx = string.byte(rx_buffer, 3)
            local cy = string.byte(rx_buffer, 4)
            local size = string.byte(rx_buffer, 5)

            rx_buffer = string.sub(rx_buffer, 6)

            if status == 1 then
                latest_marker.found = true
                latest_marker.cx = cx
                latest_marker.cy = cy
                latest_marker.size = size
                last_marker_time = now()
            else
                latest_marker.found = false
            end
        end
    end
end

local function marker_is_recent()
    return latest_marker.found and ((now() - last_marker_time) <= MARKER_TIMEOUT)
end

-- ==================== ПОЛЕТ: ОФИЦИАЛЬНЫЙ ap API + FALLBACK ====================
local function autopilot_event(event_name)
    if ap and Ev and Ev[event_name] then
        local ok = safe_call("ap.push." .. event_name, function()
            ap.push(Ev[event_name])
        end)
        if ok then
            return true
        end
    end
    return false
end

local function arm_and_takeoff()
    led_red()
    log("preflight")

    local preflight_ok = autopilot_event("MCE_PREFLIGHT")
    if not preflight_ok then
        safe_call("pioneer.arm", function()
            if pioneer and pioneer.arm then
                pioneer.arm()
            elseif pioneer and pioneer.arming then
                pioneer.arming()
            end
        end)
    end

    Timer.callLater(TAKEOFF_DELAY, function()
        led_yellow()
        log("takeoff")

        local takeoff_ok = autopilot_event("MCE_TAKEOFF")
        if not takeoff_ok then
            safe_call("pioneer.takeoff", function()
                if pioneer and pioneer.takeoff then
                    pioneer.takeoff(SEARCH_HEIGHT)
                end
            end)
        end

        state = STATE_TAKEOFF
    end)
end

local function go_to_local(x, y, z, seconds)
    target_x = x
    target_y = y
    target_z = z

    if ap and ap.goToLocalPoint then
        return safe_call("ap.goToLocalPoint", function()
            ap.goToLocalPoint(x, y, z, seconds or 1)
        end)
    end

    return safe_call("pioneer.setTargetPoint", function()
        pioneer.setTargetPoint(x, y, z, 0)
    end)
end

local function stop_motion()
    go_to_local(target_x, target_y, target_z, 1)
end

local function land()
    led_blue()
    log("landing")

    local landing_ok = autopilot_event("MCE_LANDING")
    if not landing_ok then
        safe_call("pioneer.land", function()
            if pioneer and pioneer.land then
                pioneer.land()
            end
        end)
    end
end

local function disarm()
    local disarm_ok = autopilot_event("ENGINES_DISARM")
    if not disarm_ok then
        safe_call("pioneer.disarm", function()
            if pioneer and pioneer.disarm then
                pioneer.disarm()
            end
        end)
    end
end

-- ==================== АВАРИЯ ====================
local function emergency()
    led_red()
    land()
    disarm()
    if mission_timer then
        mission_timer:stop()
    end
end

function callback(event)
    if event == Ev.LOW_VOLTAGE2 then
        emergency()
    end
end

-- ==================== МИССИЯ ====================
init_uart()
arm_and_takeoff()

Timer.callLater(SEARCH_DELAY, function()
    state = STATE_SEARCH
    target_x = 0
    target_y = 0
    target_z = SEARCH_HEIGHT
    go_to_local(target_x, target_y, target_z, 3)
    log("search")
end)

mission_timer = Timer.new(LOOP_PERIOD, function()
    parse_uart()

    if now() - start_time > MISSION_TIMEOUT then
        log("timeout")
        emergency()
        return
    end

    if state == STATE_BOOT or state == STATE_TAKEOFF then
        local t = now()
        if t - last_blink_time >= 0.3 then
            blink_on = not blink_on
            if blink_on then
                led_red()
            else
                led_yellow()
            end
            last_blink_time = t
        end
        return
    end

    if state == STATE_SEARCH then
        local t = now()
        if t - last_blink_time >= 0.35 then
            blink_on = not blink_on
            if blink_on then
                led_green()
            else
                led_off()
            end
            last_blink_time = t
        end

        if marker_is_recent() then
            state = STATE_APPROACH
            led_blue()
            log("marker found")
        end
        return
    end

    if state == STATE_APPROACH then
        led_blue()

        if not marker_is_recent() then
            state = STATE_SEARCH
            stop_motion()
            log("marker lost")
            return
        end

        local x_error = latest_marker.cx - FRAME_CX
        local y_error = latest_marker.cy - FRAME_CY
        local centered = math.abs(x_error) <= DEAD_ZONE_PX and math.abs(y_error) <= DEAD_ZONE_PX
        local close_enough = latest_marker.size >= LAND_SIZE_PX

        if centered and close_enough then
            state = STATE_LANDING
            land()
            Timer.callLater(5, function()
                disarm()
                led_blue()
                state = STATE_DONE
                mission_timer:stop()
            end)
            return
        end

        if centered then
            go_to_local(target_x, target_y, APPROACH_HEIGHT, 1)
            return
        end

        -- Если дрон уходит от метки, поменяйте знаки у step_x/step_y.
        local step_x = clamp(y_error * PIXEL_TO_METER, -MAX_STEP_M, MAX_STEP_M)
        local step_y = clamp(x_error * PIXEL_TO_METER, -MAX_STEP_M, MAX_STEP_M)

        go_to_local(target_x + step_x, target_y + step_y, APPROACH_HEIGHT, 1)
        return
    end

    if state == STATE_DONE then
        led_blue()
    end
end)

mission_timer:start()
