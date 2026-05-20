#!/usr/bin/env python3
# =============================================================
# ФАЙЛ: turtlebro_mover.py
# КУДА ЗАПУСКАТЬ: ноутбук с ROS (терминал)
# КОМАНДА: python3 turtlebro_mover.py
# НАЗНАЧЕНИЕ: Управление наземной платформой TurtleBro
# =============================================================
# СТРАТЕГИЯ: Медленный круг — мы сами задаём скорость!
# По регламенту: "постоянная скорость" — ставим минимальную.
# Скорость 0.07 м/с ≈ 7 см/с — едва движется, дрону легко поймать.
# =============================================================

import rospy
import math
import time
import signal
import sys
from geometry_msgs.msg import Twist

# ==================== ПАРАМЕТРЫ ТРАЕКТОРИИ ====================
LINEAR_SPEED  = 0.07   # м/с — ГЛАВНЫЙ ЛАЙФХАК: чем медленнее, тем лучше!
CIRCLE_RADIUS = 1.5    # метры — радиус круга
DURATION      = 1200   # секунд — 20 минут (на весь зачётный полёт)

# Angular velocity = v / r (для движения по кругу)
ANGULAR_SPEED = LINEAR_SPEED / CIRCLE_RADIUS

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
rospy.init_node('turtlebro_mission', anonymous=False)
pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
rate = rospy.Rate(10)  # 10 Гц

def stop_platform():
    """Остановить платформу (вызывается при выходе)"""
    stop_msg = Twist()
    pub.publish(stop_msg)
    rospy.loginfo("[TurtleBro] Платформа остановлена.")

def signal_handler(sig, frame):
    stop_platform()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ==================== ДВИЖЕНИЕ ====================
rospy.loginfo("=" * 50)
rospy.loginfo("[TurtleBro] Старт миссии")
rospy.loginfo(f"  Скорость:     {LINEAR_SPEED} м/с")
rospy.loginfo(f"  Радиус:       {CIRCLE_RADIUS} м")
rospy.loginfo(f"  Угл. скорость:{ANGULAR_SPEED:.4f} рад/с")
rospy.loginfo(f"  Длительность: {DURATION} с")
rospy.loginfo("=" * 50)

# Сообщение для постоянного движения по кругу
move_msg = Twist()
move_msg.linear.x  = LINEAR_SPEED   # вперёд
move_msg.angular.z = ANGULAR_SPEED  # поворот (против часовой — положительное)

start_time = time.time()

while not rospy.is_shutdown():
    elapsed = time.time() - start_time

    if elapsed >= DURATION:
        rospy.loginfo("[TurtleBro] Время вышло — останавливаю платформу.")
        break

    # Публикуем команду движения
    pub.publish(move_msg)

    # Логируем каждые 30 секунд
    if int(elapsed) % 30 == 0 and int(elapsed) > 0:
        rospy.loginfo(f"[TurtleBro] Работает: {int(elapsed)}с / {DURATION}с")

    rate.sleep()

stop_platform()
