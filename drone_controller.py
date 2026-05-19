# drone_controller.py
#from pioneer_sdk import Pioneer
from mock_pioneer import MockPioneer as Pioneer
import time

class DroneController:
    def __init__(self):
        self.drone = Pioneer()
        self.is_landing = False
    
    def takeoff(self, altitude=1.5):
        """Взлёт с красным светодиодом"""
        self.drone.led_control(r=255, g=0, b=0)  # КРАСНЫЙ
        self.drone.arm()
        self.drone.takeoff()
        time.sleep(5)  # ждём набора высоты
        print("Взлёт выполнен")
    
    def set_green_blink(self):
        """Зелёное мигание при обнаружении и посадке"""
        self.drone.led_control(r=0, g=255, b=0, mode=1)  # мигающий
    
    def go_to(self, x, y, z, yaw=0):
        """Лететь к точке в локальной системе координат"""
        self.drone.go_to_local_point(x=x, y=y, z=z, yaw=yaw)
    
    def land(self):
        self.set_green_blink()
        self.drone.land()
    
    def emergency_land(self):
        """Экстренная посадка на месте"""
        self.drone.land()