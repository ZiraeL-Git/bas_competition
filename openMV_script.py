# =============================================================
# ФАЙЛ: openMV_script.py
# КУДА: OpenMV IDE -> сохранить на камеру как main.py
#
# Метод:
#   Детектор ArUco-подобной метки для OpenMV.
#
# Важно:
#   OpenMV не имеет штатного аналога OpenCV cv2.aruco.detectMarkers().
#   Поэтому скрипт не декодирует словарь и ID ArUco. Он надежно ищет
#   саму метку как квадрат с черной рамкой и контрастной внутренней сеткой.
#   Для посадки этого достаточно: Pioneer получает центр и размер метки.
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

# Автоэкспозиция помогает при разном освещении полигона.
sensor.set_auto_gain(True)
sensor.set_auto_exposure(True)
sensor.set_auto_whitebal(False)
sensor.skip_frames(time=1000)

# -------------------- UART к Pioneer --------------------
UART_ID = 3
UART_BAUD = 115200
uart = UART(UART_ID, UART_BAUD, timeout_char=100)

# -------------------- LED OpenMV --------------------
led_red = LED(1)       # метка не найдена
led_green = LED(2)     # метка найдена

# ==================== Параметры ====================

# Поиск квадратов-кандидатов через find_rects().
# Если вообще нет кандидатов - уменьшить до 3000-5000.
# Если много ложных квадратов - увеличить до 10000-14000.
RECT_THRESHOLD = 6000

# Fallback через поиск темных blob-ов.
# Если метка слишком светлая/сероватая на камере - увеличьте верхнюю границу.
BLACK_THRESHOLD = (0, 90)

# Размер метки в кадре. Для QVGA 20 px - нижняя граница, ниже сетка читается плохо.
MIN_SIDE_PX = 20
MAX_SIDE_PX = 240

# Допуск формы: 100 = квадрат 1:1.
MIN_ASPECT_X100 = 55
MAX_ASPECT_X100 = 180

# Контраст между темными и светлыми ячейками сетки.
MIN_GRID_CONTRAST = 25

# Черная рамка ArUco занимает внешние ячейки. Проверка мягкая, потому что
# OpenMV может видеть метку под углом, с бликами и размытием.
MIN_DARK_BORDER_CELLS = 18      # максимум 20
MIN_INNER_DARK_CELLS = 2        # внутри должен быть узор, а не пустой квадрат
MAX_INNER_DARK_CELLS = 14

# Fallback blob-фильтры.
MIN_BLOB_PIXELS = 120
MIN_BLOB_FILL_X100 = 18         # черных пикселей в bbox, проценты * 100
MAX_BLOB_FILL_X100 = 85

DRAW_DEBUG = True

clock = time.clock()


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def gray_at(img, x, y):
    x = clamp(int(x), 0, img.width() - 1)
    y = clamp(int(y), 0, img.height() - 1)
    value = img.get_pixel(x, y)
    if isinstance(value, tuple):
        return (value[0] + value[1] + value[2]) // 3
    return value


def quad_point(corners, u, v):
    # corners: top-left, top-right, bottom-right, bottom-left.
    tl = corners[0]
    tr = corners[1]
    br = corners[2]
    bl = corners[3]

    one_u = 1.0 - u
    one_v = 1.0 - v

    x = (one_u * one_v * tl[0]) + (u * one_v * tr[0]) + (u * v * br[0]) + (one_u * v * bl[0])
    y = (one_u * one_v * tl[1]) + (u * one_v * tr[1]) + (u * v * br[1]) + (one_u * v * bl[1])
    return x, y


def cell_mean(img, corners, row, col):
    # Несколько точек внутри ячейки устойчивее одного пикселя.
    offsets = ((0.0, 0.0), (-0.16, 0.0), (0.16, 0.0), (0.0, -0.16), (0.0, 0.16))
    total = 0

    for du, dv in offsets:
        u = (col + 0.5 + du) / 6.0
        v = (row + 0.5 + dv) / 6.0
        x, y = quad_point(corners, u, v)
        total += gray_at(img, x, y)

    return total // len(offsets)


def grid_score(img, corners):
    means = []
    min_value = 255
    max_value = 0

    for row in range(6):
        out_row = []
        for col in range(6):
            value = cell_mean(img, corners, row, col)
            out_row.append(value)
            if value < min_value:
                min_value = value
            if value > max_value:
                max_value = value
        means.append(out_row)

    contrast = max_value - min_value
    if contrast < MIN_GRID_CONTRAST:
        return None

    threshold = (min_value + max_value) // 2
    dark_border = 0
    inner_dark = 0

    for row in range(6):
        for col in range(6):
            is_dark = means[row][col] < threshold

            if row == 0 or row == 5 or col == 0 or col == 5:
                if is_dark:
                    dark_border += 1
            else:
                if is_dark:
                    inner_dark += 1

    if dark_border < MIN_DARK_BORDER_CELLS:
        return None
    if inner_dark < MIN_INNER_DARK_CELLS or inner_dark > MAX_INNER_DARK_CELLS:
        return None

    return (dark_border * 100) + (contrast * 10) + inner_dark


def rect_is_reasonable(rect):
    w = rect.w()
    h = rect.h()

    if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
        return False
    if w > MAX_SIDE_PX or h > MAX_SIDE_PX:
        return False

    ratio_x100 = (w * 100) // h if h else 0
    if ratio_x100 < MIN_ASPECT_X100 or ratio_x100 > MAX_ASPECT_X100:
        return False

    return True


def marker_from_rect(img, rect):
    if not rect_is_reasonable(rect):
        return None

    score = grid_score(img, rect.corners())
    if score is None:
        return None

    cx_abs = rect.x() + rect.w() // 2
    cy_abs = rect.y() + rect.h() // 2
    size = (rect.w() + rect.h()) // 2

    return {
        "kind": "rect",
        "obj": rect,
        "score": score + rect.w() * rect.h(),
        "cx_abs": cx_abs,
        "cy_abs": cy_abs,
        "cx": cx_abs - (img.width() // 2),
        "cy": cy_abs - (img.height() // 2),
        "size": size,
    }


def blob_is_reasonable(blob):
    w = blob.w()
    h = blob.h()

    if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
        return False
    if w > MAX_SIDE_PX or h > MAX_SIDE_PX:
        return False

    ratio_x100 = (w * 100) // h if h else 0
    if ratio_x100 < MIN_ASPECT_X100 or ratio_x100 > MAX_ASPECT_X100:
        return False

    box_area = w * h
    if box_area <= 0:
        return False

    fill_x100 = (blob.pixels() * 100) // box_area
    if fill_x100 < MIN_BLOB_FILL_X100 or fill_x100 > MAX_BLOB_FILL_X100:
        return False

    return True


def marker_from_blob(img, blob):
    if not blob_is_reasonable(blob):
        return None

    cx_abs = blob.cx()
    cy_abs = blob.cy()
    size = (blob.w() + blob.h()) // 2
    score = blob.pixels() + size * 20

    return {
        "kind": "blob",
        "obj": blob,
        "score": score,
        "cx_abs": cx_abs,
        "cy_abs": cy_abs,
        "cx": cx_abs - (img.width() // 2),
        "cy": cy_abs - (img.height() // 2),
        "size": size,
    }


def choose_best_marker(candidates):
    best = None
    best_score = -1

    for marker in candidates:
        if marker is None:
            continue
        if marker["score"] > best_score:
            best = marker
            best_score = marker["score"]

    return best


def find_marker(img):
    candidates = []

    # Основной путь: квадрат + проверка черной рамки и сетки.
    for rect in img.find_rects(threshold=RECT_THRESHOLD):
        candidates.append(marker_from_rect(img, rect))

    best = choose_best_marker(candidates)
    if best is not None:
        return best

    # Fallback: если find_rects не поймал контур, берем самый похожий
    # черный квадратный blob. Это менее точно, но часто спасает на плохом свете.
    candidates = []
    for blob in img.find_blobs(
        [BLACK_THRESHOLD],
        pixels_threshold=MIN_BLOB_PIXELS,
        area_threshold=MIN_BLOB_PIXELS,
        merge=True,
        margin=4,
    ):
        candidates.append(marker_from_blob(img, blob))

    return choose_best_marker(candidates)


def draw_marker(img, marker):
    obj = marker["obj"]

    if marker["kind"] == "rect":
        img.draw_rectangle(obj.x(), obj.y(), obj.w(), obj.h(), color=255, thickness=2)
        corners = obj.corners()
        for i in range(4):
            a = corners[i]
            b = corners[(i + 1) % 4]
            img.draw_line(a[0], a[1], b[0], b[1], color=255, thickness=2)
    else:
        img.draw_rectangle(obj.rect(), color=255, thickness=2)

    img.draw_cross(marker["cx_abs"], marker["cy_abs"], color=255, size=12, thickness=2)
    img.draw_string(
        4, 4,
        "ARUCO {} cx={} cy={} sz={}".format(
            marker["kind"],
            marker["cx"],
            marker["cy"],
            marker["size"],
        ),
        color=255,
        scale=1,
    )


def send_found(marker, img):
    uart.write("FOUND,{},{},{}\n".format(marker["cx"], marker["cy"], marker["size"]))

    if DRAW_DEBUG:
        draw_marker(img, marker)


def send_none():
    uart.write("NONE\n")


# =============================================================
# Основной цикл
# =============================================================
while True:
    clock.tick()
    img = sensor.snapshot()

    marker = find_marker(img)

    if marker is None:
        send_none()
        led_red.on()
        led_green.off()
    else:
        send_found(marker, img)
        led_green.on()
        led_red.off()
