-- =============================================================
-- ФАЙЛ: pioneer_mission.lua
-- КУДА ЗАГРУЖАТЬ: Pioneer Station → загрузить на дрон
-- ЯЗЫК: Lua (выполняется НА БОРТУ дрона)
-- НАЗНАЧЕНИЕ: Главная логика миссии — взлёт, поиск, посадка
-- =============================================================
-- ПОСЛЕДОВАТЕЛЬНОСТЬ LED (по регламенту):
--   Взлёт          → КРАСНЫЙ
--   Поиск маркера  → ЗЕЛЁНЫЙ МИГАЮЩИЙ
--   Обнаружен+посадка → СИНИЙ ПОСТОЯННЫЙ
--   После посадки  → DISARM (отключение двигателей программно)
-- =============================================================

-- ==================== ПАРАМЕТРЫ МИССИИ ====================
local TAKEOFF_HEIGHT    = 1.5    -- высота взлёта, метры
local SEARCH_HEIGHT     = 1.5    -- высота поиска маркера, метры
local APPROACH_HEIGHT   = 0.8    -- высота при наведении, метры
local PIXEL_TO_METER    = 0.002  -- пикселей → метры (подобрать по тестам!)
local DEAD_ZONE_PX      = 30     -- мёртвая зона, пиксели (считаем "по центру")
local SIZE_CLOSE        = 130    -- размер тега в пикселях при котором мы "близко"
local BLINK_INTERVAL    = 0.4    -- интервал мигания зелёного, секунды
local MISSION_TIMEOUT   = 1100   -- таймаут миссии, секунды (≈18 мин, лимит 20)
local UART_BAUD         = 115200 -- скорость UART (должна совпадать с OpenMV)

-- ==================== СОСТОЯНИЯ МАШИНЫ ====================
local STATE = {
    TAKEOFF  = "TAKEOFF",
    SEARCH   = "SEARCH",
    APPROACH = "APPROACH",
    LANDING  = "LANDING",
    DONE     = "DONE",
}
local current_state = STATE.TAKEOFF

-- ==================== ЛОГ-ФАЙЛ ====================
-- Лог пишется в консоль Pioneer Station и в файл на SD-карте
local log_entries = {}
local mission_start = os.clock()

local function log(event, data)
    local t = string.format("%.2f", os.clock() - mission_start)
    local msg = string.format("[%ss] %s | %s", t, event, data or "")
    table.insert(log_entries, msg)
    print(msg)  -- вывод в консоль Pioneer Station (видно в реальном времени)
end

local function save_log()
    -- Сохраняем лог в файл (требование задания: +2 балла)
    local f = io.open("mission_log.txt", "w")
    if f then
        f:write("=== ЛОГ МИССИИ ===\n")
        f:write("Начало: " .. os.date() .. "\n")
        f:write("===================\n")
        for _, line in ipairs(log_entries) do
            f:write(line .. "\n")
        end
        f:write("=== КОНЕЦ ЛОГА ===\n")
        f:close()
        print("Лог сохранён: mission_log.txt")
    else
        print("ОШИБКА: не удалось сохранить лог!")
    end
end

-- ==================== LED УПРАВЛЕНИЕ ====================
-- ВНИМАНИЕ: если LED модуль подключён через расширение, используйте его API
-- Если LED встроен в Pioneer — используйте pioneer.setLedsColor

local blink_state    = false
local last_blink_time = 0

local function led_red()
    -- Взлёт: КРАСНЫЙ ПОСТОЯННЫЙ
    pioneer.setLedsColor(255, 0, 0)
end

local function led_green_blink_tick()
    -- Поиск: ЗЕЛЁНЫЙ МИГАЮЩИЙ (вызывать в каждой итерации цикла)
    local now = os.clock()
    if (now - last_blink_time) >= BLINK_INTERVAL then
        blink_state = not blink_state
        if blink_state then
            pioneer.setLedsColor(0, 255, 0)
        else
            pioneer.setLedsColor(0, 0, 0)
        end
        last_blink_time = now
    end
end

local function led_blue()
    -- Посадка: СИНИЙ ПОСТОЯННЫЙ
    pioneer.setLedsColor(0, 0, 255)
end

local function led_off()
    pioneer.setLedsColor(0, 0, 0)
end

-- ==================== UART / OpenMV ====================
-- Чтение данных от OpenMV камеры через UART

local uart = nil

local function init_uart()
    if uart then
        return true
    end

    local ok, result = pcall(function()
        return serial.open(3, UART_BAUD)  -- UART3 = порт расширения
    end)

    if ok and result then
        uart = result
        log("UART", "UART3 открыт, baud=" .. tostring(UART_BAUD))
        return true
    end

    log("UART_ERROR", tostring(result))
    return false
end

local function read_marker()
    -- Возвращает таблицу {found, cx, cy, size}
    -- found = true если маркер обнаружен
    if not uart then
        return { found = false }
    end

    local line = uart:readline()
    if not line then
        return { found = false }
    end

    line = line:gsub("[\r\n]", "")  -- убрать перенос строк

    if line == "NONE" or line == "" then
        return { found = false }
    end

    -- Формат от OpenMV: "FOUND,cx,cy,size"
    local prefix, cx, cy, size = line:match("(%u+),(-?%d+),(-?%d+),(%d+)")

    if prefix == "FOUND" then
        return {
            found = true,
            cx    = tonumber(cx),   -- смещение по X (пиксели от центра)
            cy    = tonumber(cy),   -- смещение по Y (пиксели от центра)
            size  = tonumber(size), -- размер маркера в пикселях
        }
    end

    return { found = false }
end

-- ==================== ГЛАВНАЯ ЛОГИКА МИССИИ ====================

log("MISSION_START", "Инициализация")

-- ---- 1. ВЗЛЁТ ----
led_red()  -- КРАСНЫЙ при взлёте (регламент п.3)
log("LED", "RED — взлёт")
log("TAKEOFF", string.format("Взлёт на высоту %.1f м", TAKEOFF_HEIGHT))

local arm_ok, arm_err = pcall(function()
    if pioneer.arm then
        pioneer.arm()
    end
end)
if not arm_ok then
    log("ARM_ERROR", tostring(arm_err))
end

local takeoff_ok, takeoff_err = pcall(function()
    pioneer.takeoff(TAKEOFF_HEIGHT)
end)
if not takeoff_ok then
    log("TAKEOFF_ERROR", tostring(takeoff_err))
end

timer.sleep(5000)  -- ждём стабилизации на высоте (5 секунд)

-- UART открываем только после взлёта, чтобы ошибка камеры/порта
-- не мешала увидеть старт миссии и красный LED.
init_uart()

current_state = STATE.SEARCH

-- ---- 2. ПОИСК (зелёный мигающий) ----
log("STATE", "SEARCH — начинаю поиск маркера")
log("LED", "GREEN BLINK — поиск платформы")

-- Зависаем в точке поиска
pioneer.setTargetPoint(0, 0, SEARCH_HEIGHT, 0)

-- Основной цикл
while current_state ~= STATE.DONE do

    -- Таймаут миссии — аварийная посадка
    if (os.clock() - mission_start) > MISSION_TIMEOUT then
        log("TIMEOUT", "Превышен лимит времени — аварийная посадка")
        led_off()
        pioneer.land()
        timer.sleep(4000)
        pioneer.disarm()
        save_log()
        return
    end

    -- Читаем данные с OpenMV
    if not uart then
        init_uart()
    end

    local marker = read_marker()

    -- ---- СОСТОЯНИЕ: ПОИСК ----
    if current_state == STATE.SEARCH then
        led_green_blink_tick()  -- Мигаем зелёным

        if marker.found then
            log("MARKER_FOUND", string.format(
                "Маркер обнаружен! cx=%d px, cy=%d px, size=%d px",
                marker.cx, marker.cy, marker.size))

            -- Переключаем на СИНИЙ (регламент п.5 — при обнаружении)
            led_blue()
            log("LED", "BLUE SOLID — платформа обнаружена, режим посадки")

            current_state = STATE.APPROACH
        end

    -- ---- СОСТОЯНИЕ: НАВЕДЕНИЕ ----
    elseif current_state == STATE.APPROACH then
        -- Синий постоянный горит уже с момента обнаружения

        if marker.found then
            -- Вычисляем поправку позиции
            -- Знак минус: если маркер правее центра (+cx) → двигаемся вправо
            local dx = marker.cx * PIXEL_TO_METER   -- коррекция по X
            local dy = marker.cy * PIXEL_TO_METER   -- коррекция по Y

            log("APPROACH", string.format(
                "Наведение: cx=%d cy=%d size=%d | dx=%.3f dy=%.3f",
                marker.cx, marker.cy, marker.size, dx, dy))

            -- Проверяем что маркер по центру
            local centered = math.abs(marker.cx) < DEAD_ZONE_PX and
                             math.abs(marker.cy) < DEAD_ZONE_PX

            -- Проверяем что мы достаточно низко (маркер большой в кадре)
            local close_enough = marker.size >= SIZE_CLOSE

            if centered and close_enough then
                -- ---- Начинаем посадку ----
                log("LANDING_START", "Центрирован + достаточно близко → посадка")
                current_state = STATE.LANDING

                pioneer.land()             -- команда посадки
                timer.sleep(5000)          -- ждём приземления (~5 секунд)

                -- Программное отключение двигателей (регламент п.5, штраф -2 если нет!)
                pioneer.disarm()
                log("DISARM", "Двигатели отключены программно — миссия выполнена!")

                current_state = STATE.DONE

            elseif centered then
                -- По центру, но ещё высоко — снижаемся
                pioneer.setTargetPoint(0, 0, APPROACH_HEIGHT, 0)
                log("DESCEND", "Снижаюсь...")

            else
                -- Корректируем горизонтальную позицию
                -- setVelocity(vx, vy, vz, vyaw)
                pioneer.setVelocity(dy, dx, 0, 0)
            end

        else
            -- Потеряли маркер — зависаем
            pioneer.setVelocity(0, 0, 0, 0)
            log("MARKER_LOST", "Маркер потерян — зависаю, продолжаю поиск")
            current_state = STATE.SEARCH  -- возвращаемся в поиск
            led_green_blink_tick()
        end
    end

    timer.sleep(100)  -- цикл управления ~10 Гц
end

-- ==================== ФИНАЛ ====================
-- СИНИЙ остаётся гореть после посадки и дизарма (регламент п.5 и п.12 — +2 балла)
led_blue()
log("MISSION_COMPLETE", string.format(
    "Миссия завершена за %.1f секунд",
    os.clock() - mission_start))

save_log()  -- сохраняем лог (регламент п.12 — +2 балла)
