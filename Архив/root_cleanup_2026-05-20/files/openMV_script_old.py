# =============================================================
# ФАЙЛ: openMV_script.py
# КУДА ЗАГРУЖАТЬ: OpenMV IDE → сохранить как main.py на камеру
# ЯЗЫК: MicroPython (запускается ВНУТРИ OpenMV камеры)
# НАЗНАЧЕНИЕ: Обнаружение AprilTag маркера, отправка данных
#             о положении маркера в Pioneer через UART
# =============================================================
# РАСПЕЧАТАЙТЕ МАРКЕР: AprilTag семейство TAG36H11, ID = 0
# Ссылка: https://github.com/AprilRobotics/apriltag-imgs
# Размер печати: минимум 20x20 см, чем больше — тем лучше
# =============================================================

import sensor
import image
import time
from pyb import UART, LED

# ---------- Настройка камеры ----------
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)   # 320x240 пикселей
sensor.set_vflip(True)               # Камера смотрит вниз — переворачиваем
sensor.set_hmirror(True)             # Зеркалим по горизонтали
sensor.skip_frames(time=2000)        # Ждём стабилизации экспозиции
sensor.set_auto_gain(False)          # Отключить авто-усиление (быстрее)
sensor.set_auto_whitebal(False)      # Отключить авто-баланс белого

# ---------- UART к Pioneer ----------
# Pioneer expansion port: UART3, 115200 baud
uart = UART(3, 115200, timeout_char=100)

# ---------- Встроенные LED камеры (для отладки) ----------
led_red   = LED(1)   # красный = нет маркера
led_green = LED(2)   # зелёный = маркер найден
led_blue  = LED(3)

# ---------- Параметры ----------
TARGET_TAG_ID = 0                    # ID маркера (изменить если нужен другой)
TAG_FAMILY    = image.AprilTagFamilies.TAG36H11  # семейство тегов

clock = time.clock()

# =============================================================
# ОСНОВНОЙ ЦИКЛ
# =============================================================
while True:
    clock.tick()
    img = sensor.snapshot()

    # Ищем AprilTag в кадре
    tags = img.find_apriltags(families=TAG_FAMILY)

    marker_found = False

    for tag in tags:
        if tag.id() != TARGET_TAG_ID:
            continue  # Нас интересует только наш маркер

        # Смещение центра маркера от центра кадра (в пикселях)
        # cx > 0 → маркер правее центра (дрон нужно двигать вправо)
        # cy > 0 → маркер ниже центра (дрон нужно двигать вперёд)
        cx   = tag.cx() - (img.width()  // 2)
        cy   = tag.cy() - (img.height() // 2)
        size = tag.w()   # ширина тега в пикселях (≈ мера расстояния: больше = ближе)

        # Рисуем рамку и крест на изображении (видно в OpenMV IDE)
        img.draw_rectangle(tag.rect(), color=(0, 255, 0), thickness=2)
        img.draw_cross(tag.cx(), tag.cy(), color=(255, 0, 0), size=10)
        img.draw_string(10, 10, "TAG #{} cx={} cy={} size={}".format(
            tag.id(), cx, cy, size), color=(255, 255, 0), scale=1)

        # Отправляем данные в Pioneer: "FOUND,cx,cy,size\n"
        msg = "FOUND,{},{},{}\n".format(cx, cy, size)
        uart.write(msg)

        # Индикация: зелёный LED = маркер найден
        led_green.on()
        led_red.off()

        marker_found = True
        break  # Берём только первый найденный маркер

    if not marker_found:
        # Маркер не виден — отправляем NONE
        uart.write("NONE\n")
        led_red.on()
        led_green.off()

    # FPS не нужно ограничивать — QVGA обрабатывается ~30fps
