# vision.py
import cv2
import cv2.aruco as aruco
import numpy as np

class MarkerDetector:
    def __init__(self, camera_index=0):
        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
        self.parameters = aruco.DetectorParameters()
        self.target_id = 1  # ID нашего маркера
        
        # Размер маркера в метрах (измерьте распечатанный!)
        self.marker_size = 0.30
        
    def get_marker_position(self):
        """
        Возвращает (x_offset, y_offset, distance) от центра кадра
        или None если маркер не найден.
        x_offset, y_offset в пикселях от центра
        """
        ret, frame = self.cap.read()
        if not ret:
            return None, None
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = aruco.detectMarkers(gray, self.aruco_dict, 
                                               parameters=self.parameters)
        
        if ids is None or self.target_id not in ids:
            return None, frame
        
        # Найден нужный маркер
        idx = list(ids.flatten()).index(self.target_id)
        corner = corners[idx][0]
        
        # Центр маркера в пикселях
        cx = int(np.mean(corner[:, 0]))
        cy = int(np.mean(corner[:, 1]))
        
        # Смещение от центра кадра
        frame_cx = frame.shape[1] // 2
        frame_cy = frame.shape[0] // 2
        
        x_offset = cx - frame_cx  # пикселей, >0 = маркер правее
        y_offset = cy - frame_cy  # пикселей, >0 = маркер ниже
        
        # Примерная дистанция по размеру маркера в кадре
        marker_width_px = np.linalg.norm(corner[0] - corner[1])
        # focal_length подберите экспериментально (~600 для 640px камеры)
        focal_length = 600
        distance = (self.marker_size * focal_length) / marker_width_px
        
        # Нарисовать на кадре для отладки
        aruco.drawDetectedMarkers(frame, corners, ids)
        cv2.circle(frame, (cx, cy), 10, (0, 255, 0), -1)
        cv2.putText(frame, f"dist: {distance:.2f}m", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        return {
            'x_offset': x_offset,
            'y_offset': y_offset, 
            'distance': distance,
            'cx': cx,
            'cy': cy
        }, frame
    
    def release(self):
        self.cap.release()