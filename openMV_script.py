# =============================================================
# ФАЙЛ: openMV_script.py
# КУДА: OpenMV IDE -> сохранить на камеру как main.py
#
# Метод:
#   Штатное распознавание AprilTag через OpenMV image.find_apriltags().
#
# Почему так:
#   В OpenMV есть надежный встроенный декодер AprilTag, но нет такого же
#   встроенного декодера ArUco. Для посадки на платформу AprilTag обычно
#   стабильнее, чем ручная обработка ArUco через blobs/rects.
#
# Что печатать/крепить на платформу:
#   Любой AprilTag из включенных семейств. ID может быть любым, если
#   TARGET_TAG_ID = -1. Если нужен конкретный тег, задайте TARGET_TAG_ID.
#
# UART в Pioneer:
#   FOUND,cx,cy,size\n
#   NONE\n
# =============================================================

import sensor
import image
import time
from pyb import UART, LED

# -------------------- Камера --------------------
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)
sensor.set_framesize(sensor.QVGA)       # 320x240
sensor.set_vflip(True)                  # поменяйте, если картинка перевернута
sensor.set_hmirror(True)                # поменяйте, если X уходит не туда
sensor.skip_frames(time=2000)

# Для тегов лучше зафиксировать экспозицию после короткой автонастройки.
# Если освещение сильно меняется, можно вернуть auto_gain/auto_exposure True.
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)
sensor.set_auto_exposure(True)
sensor.skip_frames(time=1000)

# -------------------- UART к Pioneer --------------------
UART_ID = 3
UART_BAUD = 115200
uart = UART(UART_ID, UART_BAUD, timeout_char=100)

# -------------------- LED OpenMV --------------------
led_red = LED(1)       # тег не найден
led_green = LED(2)     # тег найден

# ==================== Параметры ====================

# Семейства AprilTag, которые пробуем распознавать.
# Чем больше семейств включено, тем ниже FPS. Если скорость проседает,
# оставьте только то семейство, которое реально напечатано на платформе.
ENABLED_FAMILY_NAMES = (
    "TAG16H5",
    "TAG25H9",
    "TAG36H10",
    "TAG36H11",
    "TAGCIRCLE21H7",
    "TAGCIRCLE49H12",
    "TAGSTANDARD41H12",
    "TAGSTANDARD52H13",
    "TAGCUSTOM48H12",
)


def build_tag_family_mask():
    mask = 0
    for family_name in ENABLED_FAMILY_NAMES:
        try:
            mask |= getattr(image, family_name)
        except AttributeError:
            # Старые прошивки OpenMV могут не знать часть новых семейств.
            pass

    if mask == 0:
        mask = image.TAG36H11

    return mask


TAG_FAMILIES = build_tag_family_mask()

# -1 = принимать любой ID из любого включенного семейства.
# Например, поставьте 0 или 1, если на платформе должен быть конкретный ID.
TARGET_TAG_ID = -1

# Минимальная ширина/высота тега в кадре.
MIN_TAG_SIZE_PX = 12

# Чем больше decision_margin, тем увереннее распознавание.
# Для первого запуска оставляем 0.0, чтобы не отфильтровать рабочий тег.
MIN_DECISION_MARGIN = 0.0

# Некоторые семейства могут исправлять битовые ошибки. Для первого запуска
# оставляем мягкий фильтр, потом можно ужесточить до 0-1.
MAX_HAMMING = 4

# Рисовать отладку в OpenMV IDE Frame Buffer.
DRAW_DEBUG = True

clock = time.clock()


def tag_is_allowed(tag):
    if TARGET_TAG_ID >= 0 and tag.id() != TARGET_TAG_ID:
        return False

    if tag.w() < MIN_TAG_SIZE_PX or tag.h() < MIN_TAG_SIZE_PX:
        return False

    if tag.hamming() > MAX_HAMMING:
        return False

    if tag.decision_margin() < MIN_DECISION_MARGIN:
        return False

    return True


def choose_best_tag(tags):
    best = None
    best_score = -1

    for tag in tags:
        if not tag_is_allowed(tag):
            continue

        # Крупный тег с хорошим margin предпочтительнее.
        # tag.area() есть не во всех версиях прошивки OpenMV.
        score = (tag.w() * tag.h()) + int(tag.decision_margin() * 1000)
        if score > best_score:
            best = tag
            best_score = score

    return best


def tag_name(tag):
    try:
        return tag.name()
    except AttributeError:
        return "TAG"


def draw_tag(img, tag, cx, cy, size):
    img.draw_rectangle(tag.rect(), color=255, thickness=2)

    corners = tag.corners()
    for i in range(4):
        a = corners[i]
        b = corners[(i + 1) % 4]
        img.draw_line(a[0], a[1], b[0], b[1], color=255, thickness=2)

    img.draw_cross(tag.cx(), tag.cy(), color=255, size=12, thickness=2)
    img.draw_string(
        4, 4,
        "{} id={} cx={} cy={} sz={} m={} h={}".format(
            tag_name(tag),
            tag.id(),
            cx,
            cy,
            size,
            int(tag.decision_margin() * 100),
            tag.hamming(),
        ),
        color=255,
        scale=1,
    )


def send_found(tag, img):
    cx = tag.cx() - (img.width() // 2)
    cy = tag.cy() - (img.height() // 2)
    size = (tag.w() + tag.h()) // 2

    uart.write("FOUND,{},{},{}\n".format(cx, cy, size))

    if DRAW_DEBUG:
        draw_tag(img, tag, cx, cy, size)


def send_none():
    uart.write("NONE\n")


# =============================================================
# Основной цикл
# =============================================================
while True:
    clock.tick()
    img = sensor.snapshot()

    tags = img.find_apriltags(families=TAG_FAMILIES)
    tag = choose_best_tag(tags)

    if tag is None:
        send_none()
        led_red.on()
        led_green.off()
    else:
        send_found(tag, img)
        led_green.on()
        led_red.off()
