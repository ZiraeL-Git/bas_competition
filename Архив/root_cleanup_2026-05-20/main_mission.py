# main_mission.py
import time
import threading
from drone_controller import DroneController
from vision import MarkerDetector

# ---- НАСТРОЙКИ ----
SEARCH_ALTITUDE = 1.5      # высота поиска, метры
APPROACH_ALTITUDE = 0.8    # высота при наведении
LANDING_ALTITUDE = 0.3     # высота начала посадки
PIXEL_DEAD_ZONE = 30       # пикселей — "считаем что по центру"
PIXEL_TO_METER = 0.003     # коэффициент перевода (подобрать!)

class Mission:
    def __init__(self):
        self.drone = DroneController()
        self.vision = MarkerDetector(camera_index=0)
        self.marker_found = False
        self.running = True
        
    def search_pattern(self):
        """
        Паттерн поиска: змейка или спираль над зоной.
        Для начала — просто зависнуть и крутить голову.
        """
        # Простейший вариант: зависнуть в центре арены
        # Камера смотрит вниз, платформа сама приедет в поле зрения
        self.drone.go_to(x=0, y=0, z=SEARCH_ALTITUDE)
        time.sleep(3)
    
    def center_over_marker(self, marker_data):
        """
        Корректируем позицию дрона чтобы маркер был по центру.
        Простой пропорциональный регулятор (P-регулятор).
        """
        x_offset = marker_data['x_offset']
        y_offset = marker_data['y_offset']
        
        # Проверяем что маркер более-менее по центру
        if abs(x_offset) < PIXEL_DEAD_ZONE and abs(y_offset) < PIXEL_DEAD_ZONE:
            return True  # Центрировано!
        
        # Коррекция: пикселы → метры (знаки зависят от ориентации камеры!)
        dx = -x_offset * PIXEL_TO_METER
        dy = -y_offset * PIXEL_TO_METER
        
        self.drone.go_to(x=dx, y=dy, z=APPROACH_ALTITUDE)
        return False
    
    def run(self):
        print("=== МИССИЯ НАЧИНАЕТСЯ ===")
        
        # 1. ВЗЛЁТ (красный LED внутри takeoff())
        self.drone.takeoff(altitude=SEARCH_ALTITUDE)
        
        # 2. ПОИСК МАРКЕРА
        print("Ищу маркер...")
        search_timeout = time.time() + 60  # 1 минута на поиск
        
        while time.time() < search_timeout:
            marker_data, frame = self.vision.get_marker_position()
            
            if marker_data is None:
                # Маркер не виден — продолжаем поиск
                self.search_pattern()
                time.sleep(0.2)
                continue
            
            print(f"Маркер найден! Дистанция: {marker_data['distance']:.2f}м")
            
            # 3. ЗЕЛЁНЫЙ МИГАЮЩИЙ LED
            self.drone.set_green_blink()
            
            # 4. НАВЕДЕНИЕ
            centered = self.center_over_marker(marker_data)
            
            if centered and marker_data['distance'] < 1.5:
                # 5. СНИЖАЕМСЯ
                current_z = APPROACH_ALTITUDE
                print("Начинаю посадку...")
                
                while current_z > 0.15:
                    # Постоянно корректируем позицию при снижении
                    marker_data, _ = self.vision.get_marker_position()
                    if marker_data:
                        self.center_over_marker(marker_data)
                    
                    current_z -= 0.1
                    self.drone.go_to(x=0, y=0, z=max(current_z, 0.15))
                    time.sleep(0.5)
                
                # 6. ПОСАДКА
                print("ПОСАДКА!")
                self.drone.land()
                break
        
        else:
            # Маркер не найден — аварийная посадка
            print("ТАЙМАУТ! Аварийная посадка.")
            self.drone.emergency_land()
        
        self.vision.release()
        print("=== МИССИЯ ЗАВЕРШЕНА ===")

if __name__ == '__main__':
    mission = Mission()
    mission.run()