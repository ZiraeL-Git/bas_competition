# =============================================================
# ФАЙЛ: openMV_script.py — ВЕРСИЯ 3 (gaussian blur + find_blobs)
# КУДА: OpenMV IDE → сохранить как main.py на камеру
#
# ПРОБЛЕМА ПРОШЛОЙ ВЕРСИИ:
#   find_rects() видел каждую клетку ArUco отдельно,
#   а не весь маркер целиком.
#
# РЕШЕНИЕ:
#   Gaussian blur сливает внутренние клетки ArUco в одну тёмную
#   область → после инверсии threshold → find_blobs() находит
#   весь маркер как единый белый blob.
# =============================================================

import sensor
import image
import time
from pyb import UART, LED

# ---------- Камера ----------
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)  # ч/б — нужно для blur + threshold
sensor.set_framesize(sensor.QVGA)       # 320x240
sensor.set_vflip(True)                  # камера смотрит вниз
sensor.set_hmirror(True)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(True)
sensor.set_auto_exposure(True)

# ---------- UART к Pioneer (115200, UART3) ----------
uart = UART(3, 115200, timeout_char=100)

# ---------- LED OpenMV для отладки ----------
led_red   = LED(1)  # нет маркера
led_green = LED(2)  # маркер найден

# ==================== ПАРАМЕТРЫ ====================
# Порог для binary threshold (0–255).
# ArUco тёмный — ищем тёмные пиксели (ниже порога).
# Подобрать под освещение: при ярком свете увеличить до 80–100.
THRESHOLD_DARK = (0, 70)   # (min, max) — "тёмный" пиксель

# Минимальная площадь blob в пикселях.
# Весь ArUco 10x10 см с 1.5м ≈ 60x60 пикс = 3600 px²
# Ставим с запасом меньше, чтобы ловить и с большой высоты.
MIN_BLOB_PIXELS = 600

# Максимальная площадь (отсечь ложные срабатывания — пол, тень)
MAX_BLOB_PIXELS = 40000

# Степень квадратности (ширина/высота). ArUco — квадрат ≈ 1.0.
# Диапазон 0.5–2.0 допускает небольшой перекос при съёмке под углом.
SQUARENESS_MIN = 0.5
SQUARENESS_MAX = 2.0

# Размер ядра Gaussian blur (1, 2 или 3).
# 2 — оптимально: сливает клетки ArUco, но не размывает контур.
BLUR_SIZE = 2

clock = time.clock()

# =============================================================
# ОСНОВНОЙ ЦИКЛ
# =============================================================
while True:
    clock.tick()
    img = sensor.snapshot()

    # ШАГ 1: Gaussian blur — сливаем внутренние клетки ArUco
    # Без этого find_blobs() нашёл бы каждую клетку отдельно.
    img.gaussian(BLUR_SIZE)

    # ШАГ 2: Binary threshold — выделяем тёмные области (ArUco тёмный)
    # invert=False: тёмные пиксели → белые (blob ищет белое)
    img.binary([THRESHOLD_DARK], invert=False)

    # ШАГ 3: Морфология — закрываем мелкие дыры внутри маркера
    # dilate(1) → erode(1) = closing: дыры от белых клеток закрываются
    img.dilate(1)
    img.erode(1)

    # ШАГ 4: Ищем большие белые blob-ы (= тёмные области оригинала)
    blobs = img.find_blobs(
        [(255, 255)],                   # ищем белые пиксели (после binary)
        pixels_threshold=MIN_BLOB_PIXELS,
        area_threshold=MIN_BLOB_PIXELS,
        merge=True,                     # сливать соседние blob-ы
        margin=5                        # с запасом 5 пикселей
    )

    best = None
    best_score = 0

    for b in blobs:
        # Фильтр по максимальному размеру
        if b.pixels() > MAX_BLOB_PIXELS:
            continue

        # Фильтр по квадратности (ArUco — квадрат)
        ratio = b.w() / b.h() if b.h() > 0 else 0
        if ratio < SQUARENESS_MIN or ratio > SQUARENESS_MAX:
            continue

        # Выбираем самый большой подходящий blob
        if b.pixels() > best_score:
            best_score = b.pixels()
            best = b

    if best is not None:
        # Смещение центра маркера от центра кадра
        cx   = best.cx() - (img.width()  // 2)  # >0 = правее центра
        cy   = best.cy() - (img.height() // 2)  # >0 = ниже центра
        size = best.w()                           # ширина маркера, пиксели

        # Рисуем рамку и крест (видно в OpenMV IDE Frame Buffer)
        img.draw_rectangle(best.rect(), color=255, thickness=2)
        img.draw_cross(best.cx(), best.cy(), color=200, size=12)
        img.draw_string(
            4, 4,
            "cx={} cy={} sz={} px={}".format(cx, cy, size, best.pixels()),
            color=255, scale=1
        )

        # Отправляем в Pioneer Lua: "FOUND,cx,cy,size\n"
        uart.write("FOUND,{},{},{}\n".format(cx, cy, size))

        led_green.on()
        led_red.off()

    else:
        uart.write("NONE\n")
        led_red.on()
        led_green.off()
