local unpack = table.unpack

local ledNumber = 4

local leds = Ledbar.new(ledNumber)



-- Твоя рабочая функция

local function changeColor(col)

    for i=0, ledNumber - 1, 1 do

        leds:set(i, unpack(col))

    end

end



-- Инициализация UART (как в твоем примере)

local uartNum = 4

local baudRate = 9600

local uart = Uart.new(uartNum, baudRate, Uart.PARITY_NONE, 1)



-- Функция аварии

local function emergency()

    getMeasureTimer:stop()

    Timer.callLater(1, function () changeColor({1, 0, 0}) end)

end



function callback(event)

    if (event == Ev.LOW_VOLTAGE2) then

        emergency()

    end

end



-- Основной цикл (адаптирован из твоего кода)

getMeasureTimer = Timer.new(0.1, function ()

    local bytes = uart:bytesToRead()

    

    if bytes >= 2 then

        local buf = uart:read(bytes)

        -- Распаковываем координаты

        local x = string.unpack("B", buf, #buf - 1)

        

        -- Логика: если x < 80 (лево) - светим синим, если > 80 (право) - зеленым

        if x < 80 then

            changeColor({0, 0, 1}) -- СИНИЙ

        else

            changeColor({0, 1, 0}) -- ЗЕЛЕНЫЙ

        end

    else

        -- Если ничего не пришло - светим КРАСНЫМ (как в твоем старте)

        changeColor({1, 0, 0})

    end

end)



getMeasureTimer:start()