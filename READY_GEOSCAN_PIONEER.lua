local unpack = table.unpack

-- Минимальная Pioneer-часть.
-- Сейчас тут нет взлета и посадки. Только проверка:
--   1. стартует ли скрипт;
--   2. работает ли Ledbar;
--   3. доходят ли два байта cx, cy от OpenMV по UART4 9600.

local ledNumber = 4
local leds = Ledbar.new(ledNumber)

local function changeColor(col)
    for i = 0, ledNumber - 1, 1 do
        leds:set(i, unpack(col))
    end
end

-- Красный сразу после запуска: файл хотя бы начал выполняться.
changeColor({1, 0, 0})

local uartNum = 4
local baudRate = 9600
local uart = Uart.new(uartNum, baudRate, Uart.PARITY_NONE, 1)

local function emergency()
    changeColor({1, 0, 0})
    if getMeasureTimer then
        getMeasureTimer:stop()
    end
end

function callback(event)
    if event == Ev.LOW_VOLTAGE2 then
        emergency()
    end
end

getMeasureTimer = Timer.new(0.1, function()
    local bytes = uart:bytesToRead()

    if bytes >= 2 then
        local buf = uart:read(bytes)
        local x = string.unpack("B", buf, #buf - 1)
        local y = string.unpack("B", buf, #buf)

        -- Простая диагностика:
        -- синий  = метка левее центра кадра;
        -- зеленый = метка правее центра кадра;
        -- желтый = метка около центра по X.
        if x < 70 then
            changeColor({0, 0, 1})
        elseif x > 90 then
            changeColor({0, 1, 0})
        else
            changeColor({1, 1, 0})
        end

        print("OpenMV x=" .. tostring(x) .. " y=" .. tostring(y))
    else
        -- Нет данных от OpenMV.
        changeColor({1, 0, 0})
    end
end)

getMeasureTimer:start()
