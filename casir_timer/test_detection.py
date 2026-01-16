import cv2
import time
import os
os.environ['QT_QPA_PLATFORM'] = 'xcb'

from ultralytics import YOLO
import config
from video_stream import VideoStream
from detection import detect_person, draw_detections

def test():
    print("=== ТЕСТ СИСТЕМЫ ===")
    print(f"SHOW_DETECTION: {config.SHOW_DETECTION}")
    print(f"RTSP_URL: {config.RTSP_URL}")
    
    # Загружаем модель
    model = YOLO(config.MODEL_PATH, task='detect')
    
    # Запускаем видеопоток
    video_stream = VideoStream(config.RTSP_URL).start()
    time.sleep(2)
    
    try:
        for i in range(100):  # 100 кадров для теста
            ret, frame = video_stream.read()
            if not ret:
                print("Ошибка чтения кадра")
                continue
                
            # Детекция
            person_detected, max_confidence, detection_info = detect_person(
                frame, model, config.CONFIDENCE_THRESHOLD, config.ROI
            )
            
            print(f"Кадр {i}: Детекция = {person_detected}, уверенность = {max_confidence:.2f}")
            
            # Показываем окно
            debug_frame = draw_detections(
                frame.copy(), detection_info, person_detected, config.ROI,
                0, 0, False
            )
            cv2.imshow('Test Detection', debug_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        video_stream.release()
        cv2.destroyAllWindows()
        print("Тест завершен")

if __name__ == "__main__":
    test()
