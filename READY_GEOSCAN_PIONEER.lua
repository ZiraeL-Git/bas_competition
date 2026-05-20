-- =============================================================
-- READY_GEOSCAN_PIONEER.lua
-- Готовый бортовой скрипт для Geoscan Pioneer.
--
-- Основа:
--   - LED/UART/Timer взяты из Ваниного рабочего примера.
--   - Логика миссии: взлет -> поиск метки -> наведение -> посадка.
--
-- Протокол OpenMV -> Pioneer, UART4 9600:
--   0xAA, status, cx, cy, size
--   status = 1: метка найдена
--   status = 0: метка не найдена
--   cx, cy = координаты центра в кадре 160x120
--   size = примерный размер метки в пикселях
-- =============================================================

local unpack = table.unpack

-- ==================== ПАРАМЕТРЫ ====================
local LED_COUNT = 4
local UART_NUM = 4
local UART_BAUD = 9600

local FRAME_W = 160
local FRAME_H = 120
local FRAME_CX = 80
local FRAME_CY = 60

local TAKEOFF_HEIGHT = 1.2
local SEARCH_HEIGHT = 1.2
local APPROACH_HEIGHT = 0.7

local DEAD_ZONE_PX = 12
local LAND_SIZE_PX = 70
local PIXEL_TO_SPEED = 0.004
local MAX_SPEED = 0.25

local LOOP_PERIOD = 0.1
local MARKER_TIMEOUT = 0.7
local MISSION_TIMEOUT = 180

-- ==================== ОБОРУДОВАНИЕ ====================
local leds = Ledbar.new(LED_COUNT)
local uart = Uart.new(UART_NUM, UART_BAUD, Uart.PARITY_NONE, 1)

-- ==================== СОСТОЯНИЕ ====================
local STATE_TAKEOFF = "TAKEOFF"
local STATE_SEARCH = "SEARCH"
local STATE_APPROACH = "APPROACH"
local STATE_LANDING = "LANDING"
local STATE_DONE = "DONE"

local state = STATE_TAKEOFF
local start_time = os.clock()
local last_marker_time = -1000
local blink_on = false
local last_blink_time = 0
local rx_buffer = ""
local latest_marker = {
    found = false,
    cx = FRAME_CX,
    cy = FRAME_CY,
    size = 0,
}

-- ==================== УТИЛИТЫ ====================
local function clamp(v, lo, hi)
    if v < lo then
        return lo
    end
    if v > hi then
        return hi
    end
    return v
end

local function log(msg)
    print("[MISSION] " .. tostring(msg))
end

local function safe_call(name, fn)
    local ok, err = pcall(fn)
    if not ok then
        log(name .. " ERROR: " .. tostring(err))
        return false
    end
    return true
end

-- ==================== LED ====================
local function change_color(col)
    for i = 0, LED_COUNT - 1, 1 do
        leds:set(i, unpack(col))
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

local function led_off()
    change_color({0, 0, 0})
end

local function led_green_blink()
    local now = os.clock()
    if now - last_blink_time >= 0.35 then
        blink_on = not blink_on
        if blink_on then
            led_green()
        else
            led_off()
        end
        last_blink_time = now
    end
end

-- ==================== ПОЛЕТНЫЕ КОМАНДЫ ====================
local function arm()
    if pioneer and pioneer.arm then
        local ok = safe_call("pioneer.arm", function()
            pioneer.arm()
        end)
        if ok then
            return
        end
    end

    if pioneer and pioneer.arming then
        safe_call("pioneer.arming", function()
            pioneer.arming()
        end)
    end
end

local function takeoff(height)
    local ok = safe_call("pioneer.takeoff(height)", function()
        pioneer.takeoff(height)
    end)
    if ok then
        return
    end

    safe_call("pioneer.takeoff()", function()
        pioneer.takeoff()
    end)
end

local function hold_point(z)
    safe_call("setTargetPoint", function()
        pioneer.setTargetPoint(0, 0, z, 0)
    end)
end

local function set_velocity(vx, vy, vz)
    safe_call("setVelocity", function()
        pioneer.setVelocity(vx, vy, vz, 0)
    end)
end

local function land()
    safe_call("land", function()
        pioneer.land()
    end)
end

local function disarm()
    safe_call("disarm", function()
        if pioneer and pioneer.disarm then
            pioneer.disarm()
        end
    end)
end

-- ==================== UART ПРОТОКОЛ ====================
local function parse_uart()
    local bytes = uart:bytesToRead()
    if bytes <= 0 then
        return
    end

    rx_buffer = rx_buffer .. uart:read(bytes)

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
                last_marker_time = os.clock()
            else
                latest_marker.found = false
            end
        end
    end
end

local function marker_is_recent()
    return latest_marker.found and ((os.clock() - last_marker_time) <= MARKER_TIMEOUT)
end

-- ==================== АВАРИЯ ====================
local function emergency()
    led_red()
    set_velocity(0, 0, 0)
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
log("start")
led_red()
arm()
takeoff(TAKEOFF_HEIGHT)

Timer.callLater(5, function()
    state = STATE_SEARCH
    hold_point(SEARCH_HEIGHT)
    log("search")
end)

mission_timer = Timer.new(LOOP_PERIOD, function()
    parse_uart()

    if os.clock() - start_time > MISSION_TIMEOUT then
        log("timeout")
        emergency()
        return
    end

    if state == STATE_TAKEOFF then
        led_red()
        return
    end

    if state == STATE_SEARCH then
        led_green_blink()
        hold_point(SEARCH_HEIGHT)

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
            set_velocity(0, 0, 0)
            state = STATE_SEARCH
            log("marker lost")
            return
        end

        local x_error = latest_marker.cx - FRAME_CX
        local y_error = latest_marker.cy - FRAME_CY
        local centered = math.abs(x_error) <= DEAD_ZONE_PX and math.abs(y_error) <= DEAD_ZONE_PX
        local close_enough = latest_marker.size >= LAND_SIZE_PX

        if centered and close_enough then
            state = STATE_LANDING
            log("landing")
            set_velocity(0, 0, 0)
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
            hold_point(APPROACH_HEIGHT)
            return
        end

        -- ВАЖНО: знаки могут потребовать инверсии после реального теста.
        -- Если дрон уходит от метки, поменяйте знаки у vx/vy.
        local vx = clamp(y_error * PIXEL_TO_SPEED, -MAX_SPEED, MAX_SPEED)
        local vy = clamp(x_error * PIXEL_TO_SPEED, -MAX_SPEED, MAX_SPEED)

        set_velocity(vx, vy, 0)
        return
    end

    if state == STATE_DONE then
        led_blue()
    end
end)

mission_timer:start()
