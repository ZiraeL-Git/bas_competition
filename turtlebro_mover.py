# turtlebro_mover.py
import rospy
from geometry_msgs.msg import Twist
import math
import time

def move_circle(radius=1.0, speed=0.08, duration=300):
    """
    Движение по кругу. 
    speed=0.08 м/с — ОЧЕНЬ медленно, дрону легко поймать.
    duration — сколько секунд ехать (5 минут = 300)
    """
    rospy.init_node('turtlebro_trajectory', anonymous=True)
    pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
    rate = rospy.Rate(10)
    
    twist = Twist()
    # Линейная скорость
    twist.linear.x = speed
    # Угловая скорость для круга: omega = v / r
    twist.angular.z = speed / radius
    
    rospy.loginfo(f"Старт: скорость {speed} м/с, радиус {radius} м")
    
    start = time.time()
    while not rospy.is_shutdown() and (time.time() - start) < duration:
        pub.publish(twist)
        rate.sleep()
    
    # Стоп
    pub.publish(Twist())
    rospy.loginfo("Платформа остановлена")

def move_square(side=1.0, speed=0.08):
    """
    Альтернатива: движение по квадрату.
    Ещё проще для дрона — прямые отрезки.
    """
    rospy.init_node('turtlebro_square', anonymous=True)
    pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
    rate = rospy.Rate(10)
    
    time_per_side = side / speed
    
    def drive_straight(duration):
        twist = Twist()
        twist.linear.x = speed
        end = time.time() + duration
        while time.time() < end:
            pub.publish(twist)
            rate.sleep()
    
    def turn_90():
        twist = Twist()
        twist.angular.z = 0.5
        # 90 градусов = pi/2 рад, время = (pi/2) / 0.5
        end = time.time() + (math.pi / 2) / 0.5
        while time.time() < end:
            pub.publish(twist)
            rate.sleep()
        pub.publish(Twist())
        time.sleep(0.5)
    
    for _ in range(4):  # 4 стороны квадрата
        drive_straight(time_per_side)
        turn_90()

if __name__ == '__main__':
    move_circle(radius=1.5, speed=0.08)  # НАЧНИТЕ С ЭТОГО