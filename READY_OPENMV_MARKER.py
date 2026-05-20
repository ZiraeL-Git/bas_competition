import sensor
import image
import time
from pyb import UART, LED

# Минимальная OpenMV-часть.
# Задача этого файла только одна:
# найти прямоугольную метку и отправить два байта cx, cy на Pioneer.

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QQVGA)  # 160x120
sensor.skip_frames(time=2000)

uart = UART(3, 9600, timeout_char=1000)

led_red = LED(1)
led_green = LED(2)

def send_xy(x, y):
    uart.write(bytearray([x, y]))


while True:
    img = sensor.snapshot()
    rects = img.find_rects(threshold=40000)
    cx = 80
    cy = 60
    found = False

    if rects:
        r = rects[0]
        cx = r.x() + r.w() // 2
        cy = r.y() + r.h() // 2
        found = True

        print("X=%d Y=%d" % (cx, cy))

        img.draw_rectangle(r.rect())
        img.draw_cross(cx, cy)

    send_xy(cx, cy)

    if found:
        led_green.on()
        led_red.off()
    else:
        led_red.on()
        led_green.off()

    time.sleep_ms(50)
