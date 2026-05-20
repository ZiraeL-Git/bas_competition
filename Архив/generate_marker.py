# generate_marker.py — запустить один раз, распечатать
import cv2
import cv2.aruco as aruco
import numpy as np

aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
marker_img = aruco.generateImageMarker(aruco_dict, id=1, sidePixels=500)
cv2.imwrite("marker_id1.png", marker_img)
print("Маркер сохранён — распечатайте marker_id1.png на A4, максимальный размер!")