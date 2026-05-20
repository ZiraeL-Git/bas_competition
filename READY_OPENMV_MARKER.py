# =============================================================
# READY_OPENMV_MARKER.py
# Готовый скрипт для OpenMV под Geoscan Pioneer.
#
# Основа:
#   - Ванин OpenMV-пример: sensor + find_rects + UART3 9600.
#   - Протокол расширен до надежного пакета:
#       0xAA, status, cx, cy, size
#
# На стороне Pioneer:
#   UART4 9600, чтение бинарных пакетов.
# =============================================================

import sensor
import image
import time
from pyb import UART, LED

# -------------------- Камера --------------------
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)
sensor.set_framesize(sensor.QQVGA)  # 160x120
sensor.skip_frames(time=2000)
sensor.set_auto_gain(True)
sensor.set_auto_exposure(True)

# Если картинка на дроне перевернута, раскомментируйте:
# sensor.set_vflip(True)
# sensor.set_hmirror(True)

# -------------------- UART --------------------
uart = UART(3, 9600, timeout_char=1000)

# -------------------- LED OpenMV --------------------
led_red = LED(1)
led_green = LED(2)

# -------------------- Параметры поиска --------------------
FRAME_W = 160
FRAME_H = 120

# find_rects хорошо ловит AprilTag/ArUco-подобные квадратные рамки.
# Если прямоугольников нет, снижайте до 25000-30000.
RECT_THRESHOLD = 35000
MIN_SIDE = 12
MAX_SIDE = 130
MIN_ASPECT_X100 = 55
MAX_ASPECT_X100 = 180

# Если нужно ловить только крупную метку, поднимите MIN_SIDE.
SEND_EVERY_MS = 80

clock = time.clock()
last_send = time.ticks_ms()


def clamp_byte(value):
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def send_packet(found, cx=0, cy=0, size=0):
    status = 1 if found else 0
    uart.write(bytearray([
        0xAA,
        status,
        clamp_byte(cx),
        clamp_byte(cy),
        clamp_byte(size),
    ]))


def rect_is_good(rect):
    w = rect.w()
    h = rect.h()

    if w < MIN_SIDE or h < MIN_SIDE:
        return False
    if w > MAX_SIDE or h > MAX_SIDE:
        return False

    ratio = (w * 100) // h if h else 0
    if ratio < MIN_ASPECT_X100 or ratio > MAX_ASPECT_X100:
        return False

    return True


def choose_best_rect(rects):
    best = None
    best_score = -1

    for rect in rects:
        if not rect_is_good(rect):
            continue

        score = rect.w() * rect.h()
        if score > best_score:
            best = rect
            best_score = score

    return best


while True:
    clock.tick()
    img = sensor.snapshot()

    rects = img.find_rects(threshold=RECT_THRESHOLD)
    rect = choose_best_rect(rects)

    now = time.ticks_ms()
    should_send = time.ticks_diff(now, last_send) >= SEND_EVERY_MS

    if rect is not None:
        cx = rect.x() + rect.w() // 2
        cy = rect.y() + rect.h() // 2
        size = (rect.w() + rect.h()) // 2

        img.draw_rectangle(rect.rect(), color=255)
        img.draw_cross(cx, cy, color=255)
        img.draw_string(2, 2, "X:%d Y:%d S:%d" % (cx, cy, size), color=255)

        if should_send:
            send_packet(True, cx, cy, size)
            last_send = now

        led_green.on()
        led_red.off()

    else:
        if should_send:
            send_packet(False)
            last_send = now

        led_red.on()
        led_green.off()
