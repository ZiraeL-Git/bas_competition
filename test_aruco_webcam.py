# Открой marker_id1.png на телефоне и поднеси к веб-камере ноутбука
import cv2
import cv2.aruco as aruco

cap = cv2.VideoCapture(0)  # встроенная веб-камера
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
params = aruco.DetectorParameters()

while True:
    ret, frame = cap.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = aruco.detectMarkers(gray, aruco_dict, parameters=params)
    
    if ids is not None:
        aruco.drawDetectedMarkers(frame, corners, ids)
        print(f"✅ МАРКЕР НАЙДЕН! ID: {ids.flatten()}")
    else:
        print("❌ маркер не виден")
    
    cv2.imshow("ArUco Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()