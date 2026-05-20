# =============================================================
# ФАЙЛ: openMV_script.py — ВЕРСИЯ ДЛЯ ARUCO (find_rects)
# КУДА: OpenMV IDE → сохранить как main.py на камеру
# ЯЗЫК: MicroPython (внутри OpenMV камеры)
#
# ПОЧЕМУ ЭТО РАБОТАЕТ:
#   ArUco маркер = чёрная рамка + контрастный узор внутри
#   find_rects() ищет высококонтрастные квадраты — идеально!
#   Декодировать ID не нужно — нам нужно только найти и сесть.
# =============================================================

import sensor
import image
import time
from pyb import UART, LED

# ---------- Камера ----------
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)  # ч/б — быстрее для find_rects!
sensor.set_framesize(sensor.QVGA)       # 320x240
sensor.set_vflip(True)
sensor.set_hmirror(True)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(True)              # авто-усиление помогает при разном освещении
sensor.set_auto_exposure(True)

# ---------- UART к Pioneer ----------
uart = UART(3, 115200, timeout_char=100)

# ---------- LED для отладки ----------
led_red   = LED(1)   # нет маркера
led_green = LED(2)   # маркер найден

# ---------- Параметры подбираются на месте ----------
RECT_THRESHOLD  = 8000  # порог контрастности (увеличить если ложные срабатывания)
MIN_RECT_SIZE   = 25    # минимальная сторона квадрата, пикселей (отсечь мусор)
MAX_RECT_SIZE   = 250   # максимальная (отсечь края кадра)
SQUARENESS      = 0.6   # насколько прямоугольник должен быть квадратом (0..1)

clock = time.clock()

while True:
    clock.tick()
    img = sensor.snapshot()

    # Ищем прямоугольники с высоким контрастом
    # ArUco: чёрная рамка на белом фоне = очень высокий градиент
    rects = img.find_rects(threshold=RECT_THRESHOLD)

    best = None
    best_score = 0

    for r in rects:
        w = r.w()
        h = r.h()

        # --- Фильтр 1: размер ---
        if w < MIN_RECT_SIZE or h < MIN_RECT_SIZE:
            continue
        if w > MAX_RECT_SIZE or h > MAX_RECT_SIZE:
            continue

        # --- Фильтр 2: квадратность (ArUco - квадрат!) ---
        ratio = min(w, h) / max(w, h)
        if ratio < SQUARENESS:
            continue

        # --- Выбираем самый большой подходящий (ближе к дрону) ---
        score = w * h
        if score > best_score:
            best_score = score
            best = r

    if best is not None:
        # Смещение центра маркера от центра кадра
        cx   = best.cx() - (img.width()  // 2)  # >0 = правее
        cy   = best.cy() - (img.height() // 2)  # >0 = ниже
        size = best.w()                           # ширина маркера в пикселях

        # Визуализация в OpenMV IDE (для отладки)
        img.draw_rectangle(best.rect(), color=255, thickness=2)
        img.draw_cross(best.cx(), best.cy(), color=200, size=12)
        img.draw_string(
            4, 4,
            "cx={} cy={} sz={}".format(cx, cy, size),
            color=255, scale=1
        )

        # Отправляем в Pioneer: "FOUND,cx,cy,size\n"
        uart.write("FOUND,{},{},{}\n".format(cx, cy, size))

        led_green.on()
        led_red.off()

    else:
        uart.write("NONE\n")
        led_red.on()
        led_green.off()

    # ~15-20 fps в grayscale QVGA — достаточно для управления
