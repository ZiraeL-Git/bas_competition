# mock_pioneer.py
import time

class MockPioneer:
    """Имитатор дрона для тестов без железа"""
    
    def __init__(self):
        print("[MOCK] Дрон подключён (симуляция)")
        self.x, self.y, self.z = 0, 0, 0
    
    def arm(self):
        print("[MOCK] Моторы запущены")
    
    def takeoff(self):
        self.z = 1.5
        print(f"[MOCK] Взлёт! Высота: {self.z}м")
    
    def led_control(self, r=0, g=0, b=0, mode=0):
        color = "КРАСНЫЙ" if r > 0 else "ЗЕЛЁНЫЙ" if g > 0 else "выкл"
        blink = " МИГАЮЩИЙ" if mode == 1 else ""
        print(f"[MOCK] LED → {color}{blink}")
    
    def go_to_local_point(self, x, y, z, yaw=0):
        self.x, self.y, self.z = x, y, z
        print(f"[MOCK] Лечу к ({x:.2f}, {y:.2f}, {z:.2f})")
        time.sleep(0.3)  # имитация времени полёта
    
    def land(self):
        print("[MOCK] ПОСАДКА!")
        self.z = 0