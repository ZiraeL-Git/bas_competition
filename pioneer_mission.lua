-- =============================================================
-- ФАЙЛ: pioneer_mission.lua
-- РЕЖИМ: минимальный проверочный старт дрона
--
-- Зачем:
--   Если полная миссия не дает красный LED и взлет, сначала нужно
--   проверить, запускает ли Pioneer Station Lua-команды вообще.
--
-- Что делает:
--   1. Печатает сообщения в консоль.
--   2. Пробует включить красный LED разными безопасными вызовами.
--   3. Пробует ARM.
--   4. Пробует TAKEOFF.
--   5. Ждет 10 секунд.
--   6. Пробует LAND.
--
-- В этом файле специально нет UART, OpenMV, логов на SD-карту и цикла
-- распознавания, чтобы ничто не мешало старту.
-- =============================================================

local TAKEOFF_HEIGHT = 1.0
local HOLD_TIME_MS = 10000

local function say(message)
    print("[START_TEST] " .. tostring(message))
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
    say("try " .. name)

    local ok, err = pcall(fn)
    if ok then
        say(name .. " OK")
        return true
    end

    say(name .. " ERROR: " .. tostring(err))
    return false
end

local function set_led(r, g, b)
    -- У разных версий Pioneer/прошивок имена LED API могут отличаться.
    -- Пробуем несколько вариантов, ошибки не останавливают взлет.
    local ok = false

    ok = try_call("pioneer.setLedsColor", function()
        pioneer.setLedsColor(r, g, b)
    end) or ok

    ok = try_call("pioneer.setLedColor", function()
        pioneer.setLedColor(r, g, b)
    end) or ok

    ok = try_call("pioneer.led_control", function()
        pioneer.led_control(r, g, b)
    end) or ok

    return ok
end

local function arm()
    local ok = false

    ok = try_call("pioneer.arm", function()
        pioneer.arm()
    end) or ok

    ok = try_call("pioneer.arming", function()
        pioneer.arming()
    end) or ok

    return ok
end

local function takeoff()
    local ok = false

    ok = try_call("pioneer.takeoff(height)", function()
        pioneer.takeoff(TAKEOFF_HEIGHT)
    end) or ok

    if not ok then
        ok = try_call("pioneer.takeoff()", function()
            pioneer.takeoff()
        end) or ok
    end

    return ok
end

local function land()
    local ok = false

    ok = try_call("pioneer.land", function()
        pioneer.land()
    end) or ok

    ok = try_call("pioneer.disarm", function()
        pioneer.disarm()
    end) or ok

    return ok
end

-- ==================== СТАРТ ====================

say("SCRIPT STARTED")
say("If you see this in Pioneer Station, Lua script is running.")

set_led(255, 0, 0)
safe_sleep(1000)

arm()
safe_sleep(1000)

local takeoff_ok = takeoff()

if takeoff_ok then
    say("TAKEOFF COMMAND SENT")
else
    say("TAKEOFF COMMAND FAILED")
end

safe_sleep(HOLD_TIME_MS)

set_led(0, 0, 255)
safe_sleep(500)

land()

say("SCRIPT FINISHED")
