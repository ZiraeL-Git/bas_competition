# =============================================================
# ФАЙЛ: openMV_script.py
# КУДА: OpenMV IDE -> сохранить как main.py на камеру
#
# Назначение:
#   Находит ArUco 4x4 маркер OpenCV DICT_4X4_50 ID=1.
#   В отличие от старой версии, это не blob/прямоугольник "примерно
#   похожий на маркер", а проверка структуры ArUco:
#     1) найден квадрат-кандидат;
#     2) из него читается сетка 6x6;
#     3) проверяется черная рамка;
#     4) payload 4x4 сравнивается с ID=1 с учетом поворота.
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
sensor.set_framesize(sensor.QVGA)       # 320x240: баланс скорости и размера тега
sensor.set_vflip(True)                  # подберите под фактическую установку камеры
sensor.set_hmirror(True)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(True)
sensor.set_auto_exposure(True)

# -------------------- UART к Pioneer --------------------
UART_ID = 3
UART_BAUD = 115200
uart = UART(UART_ID, UART_BAUD, timeout_char=100)

# -------------------- LED OpenMV --------------------
led_red = LED(1)     # маркер не найден
led_green = LED(2)   # маркер найден

# ==================== Настройки поиска ====================

# Порог силы ребер для find_rects(). Если кандидатов нет - уменьшить,
# если много ложных прямоугольников - увеличить.
RECT_THRESHOLD = 8000

# Размер кандидата в пикселях. Для QVGA лучше не опускаться слишком низко:
# если тег меньше 28-32 px, 6x6 сетка читается нестабильно.
MIN_SIDE_PX = 28
MAX_SIDE_PX = 230

# Допуск по форме квадрата: 100 = идеально 1:1.
# 45..220 допускает перспективу и наклон камеры.
MIN_ASPECT_X100 = 45
MAX_ASPECT_X100 = 220

# Минимальная разница между темными и светлыми ячейками.
# Если освещение слабое - можно снизить до 30.
MIN_GRID_CONTRAST = 40

# Сколько ошибок payload допускаем. Для зачета лучше 0.
# Если камера шумит, можно временно поставить 1 для тестов.
MAX_PAYLOAD_ERRORS = 0

# Если True, принимается любой 4x4 ArUco-подобный маркер с черной рамкой.
# Для соревнования лучше False, чтобы не ловить случайные квадраты.
ACCEPT_ANY_4X4_ARUCO = False

# 1 = черная ячейка, 0 = белая ячейка.
# Это payload OpenCV ArUco DICT_4X4_50, ID=1.
KNOWN_MARKERS = (
    (1, (
        (1, 1, 1, 1),
        (0, 0, 0, 0),
        (0, 1, 1, 0),
        (0, 1, 0, 1),
    )),
)

# Точки внутри каждой ячейки: центр + 4 небольших смещения.
# Это устойчивее одного пикселя, но все еще быстро.
SAMPLE_POINTS = (
    (0.00, 0.00),
    (-0.18, 0.00),
    (0.18, 0.00),
    (0.00, -0.18),
    (0.00, 0.18),
)

clock = time.clock()


def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


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
    total = 0
    count = 0

    for du, dv in SAMPLE_POINTS:
        u = (col + 0.5 + du) / 6.0
        v = (row + 0.5 + dv) / 6.0
        x, y = quad_point(corners, u, v)
        total += gray_at(img, x, y)
        count += 1

    return total // count


def read_grid_6x6(img, corners):
    means = []
    min_v = 255
    max_v = 0

    for row in range(6):
        out_row = []
        for col in range(6):
            value = cell_mean(img, corners, row, col)
            out_row.append(value)
            if value < min_v:
                min_v = value
            if value > max_v:
                max_v = value
        means.append(out_row)

    contrast = max_v - min_v
    if contrast < MIN_GRID_CONTRAST:
        return None, contrast

    threshold = (min_v + max_v) // 2
    grid = []

    for row in range(6):
        out_row = []
        for col in range(6):
            out_row.append(1 if means[row][col] < threshold else 0)
        grid.append(out_row)

    return grid, contrast


def has_black_border(grid):
    for i in range(6):
        if grid[0][i] != 1:
            return False
        if grid[5][i] != 1:
            return False
        if grid[i][0] != 1:
            return False
        if grid[i][5] != 1:
            return False
    return True


def payload_from_grid(grid):
    payload = []
    for row in range(1, 5):
        out_row = []
        for col in range(1, 5):
            out_row.append(grid[row][col])
        payload.append(out_row)
    return payload


def rotate_payload_cw(payload):
    rotated = []
    for row in range(4):
        out_row = []
        for col in range(4):
            out_row.append(payload[3 - col][row])
        rotated.append(out_row)
    return rotated


def payload_error(a, b):
    errors = 0
    for row in range(4):
        for col in range(4):
            if a[row][col] != b[row][col]:
                errors += 1
    return errors


def identify_payload(payload):
    for marker_id, pattern in KNOWN_MARKERS:
        candidate = payload
        for rotation in range(4):
            if payload_error(candidate, pattern) <= MAX_PAYLOAD_ERRORS:
                return marker_id, rotation
            candidate = rotate_payload_cw(candidate)

    if ACCEPT_ANY_4X4_ARUCO:
        return -1, 0

    return None, None


def decode_aruco_4x4(img, rect):
    grid, contrast = read_grid_6x6(img, rect.corners())
    if grid is None:
        return None

    if not has_black_border(grid):
        return None

    marker_id, rotation = identify_payload(payload_from_grid(grid))
    if marker_id is None:
        return None

    return marker_id, rotation, contrast


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


def find_best_marker(img):
    best = None
    best_data = None
    best_score = 0

    for rect in img.find_rects(threshold=RECT_THRESHOLD):
        if not rect_is_reasonable(rect):
            continue

        decoded = decode_aruco_4x4(img, rect)
        if decoded is None:
            continue

        marker_id, rotation, contrast = decoded
        score = rect.w() * rect.h() + contrast * 20 + rect.magnitude()

        if score > best_score:
            best = rect
            best_data = marker_id, rotation, contrast
            best_score = score

    if best is None:
        return None

    marker_id, rotation, contrast = best_data
    cx_abs = best.x() + best.w() // 2
    cy_abs = best.y() + best.h() // 2
    cx = cx_abs - (img.width() // 2)
    cy = cy_abs - (img.height() // 2)
    size = (best.w() + best.h()) // 2

    return {
        "rect": best,
        "id": marker_id,
        "rotation": rotation,
        "contrast": contrast,
        "cx_abs": cx_abs,
        "cy_abs": cy_abs,
        "cx": cx,
        "cy": cy,
        "size": size,
    }


def draw_marker(img, marker):
    rect = marker["rect"]
    img.draw_rectangle(rect.x(), rect.y(), rect.w(), rect.h(), color=255, thickness=2)

    corners = rect.corners()
    for i in range(4):
        a = corners[i]
        b = corners[(i + 1) % 4]
        img.draw_line(a[0], a[1], b[0], b[1], color=255, thickness=2)

    img.draw_cross(marker["cx_abs"], marker["cy_abs"], color=255, size=12, thickness=2)
    img.draw_string(
        4, 4,
        "ARUCO id={} cx={} cy={} sz={} c={}".format(
            marker["id"],
            marker["cx"],
            marker["cy"],
            marker["size"],
            marker["contrast"],
        ),
        color=255,
        scale=1,
    )


# =============================================================
# Основной цикл
# =============================================================
while True:
    clock.tick()
    img = sensor.snapshot()

    marker = find_best_marker(img)

    if marker is not None:
        draw_marker(img, marker)
        uart.write("FOUND,{},{},{}\n".format(marker["cx"], marker["cy"], marker["size"]))
        led_green.on()
        led_red.off()
    else:
        uart.write("NONE\n")
        led_red.on()
        led_green.off()
