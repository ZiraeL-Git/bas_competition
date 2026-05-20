import sensor, image, time
from pyb import UART

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QQVGA) # 160x120
sensor.skip_frames(time = 2000)

uart = UART(3, 9600, timeout_char=1000)

while(True):
    img = sensor.snapshot()
    rects = img.find_rects(threshold = 40000)

    if rects:
        for r in rects:
            cx = r.x() + r.w() // 2
            cy = r.y() + r.h() // 2

            # Печать в монитор OpenMV IDE
            print("Передаю: X=%d Y=%d" % (cx, cy))

            # Отправка координат байтами
            uart.writechar(cx)
            uart.writechar(cy)

            img.draw_rectangle(r.rect())
            img.draw_cross(cx, cy)
            break # Работаем с первым найденным объектом
