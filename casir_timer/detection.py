import cv2
import numpy as np
from config import CONFIDENCE_THRESHOLD, ROI

def create_roi_mask(frame_shape, roi_points):
    """
    Создает маску для области интереса (ROI) на основе многоугольника
    """
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    if roi_points is not None:
        # Преобразуем точки в формат, подходящий для cv2.fillPoly
        pts = np.array(roi_points, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
    return mask

def detect_person(frame, model, confidence_threshold=CONFIDENCE_THRESHOLD, roi=None):
    """
    Детекция человека на кадре с порогом уверенности и областью интереса (ROI)
    """
    person_count = 0
    max_confidence = 0.0
    detection_info = []
    
    # Если задана область интереса, создаем маску
    if roi is not None:
        mask = create_roi_mask(frame.shape, roi)
        # Применяем маску к кадру
        masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
        results = model(masked_frame, verbose=False)
    else:
        results = model(frame, verbose=False)
    
    for result in results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                confidence = box.conf[0].item()
                
                if cls == 0 and confidence >= confidence_threshold:  # класс 'person' с порогом уверенности
                    person_count += 1
                    max_confidence = max(max_confidence, confidence)
                    
                    # Получаем координаты bounding box
                    x1_box, y1_box, x2_box, y2_box = map(int, box.xyxy[0])
                    
                    # Сохраняем информацию о детекции для отрисовки
                    detection_info.append({
                        'bbox': (x1_box, y1_box, x2_box, y2_box),
                        'confidence': confidence
                    })
    
    return person_count > 0, max_confidence, detection_info

def draw_detections(frame, detection_info, person_detected, roi=None, absence_minutes=0, timeout_remaining=0, is_absent=False):
    """
    Отрисовка bounding boxes, информации на кадре и области интереса (ROI)
    """
    # Рисуем область интереса (ROI) если задана
    if roi is not None:
        # Преобразуем точки в формат, подходящий для cv2.polylines
        pts = np.array(roi, dtype=np.int32)
        cv2.polylines(frame, [pts], True, (255, 255, 0), 2)  # Голубой цвет для ROI
        cv2.putText(frame, 'ROI', (roi[0][0], roi[0][1]-10), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 0), 2)
    
    # Рисуем bounding boxes
    for detection in detection_info:
        x1, y1, x2, y2 = detection['bbox']
        confidence = detection['confidence']
        
        color = (0, 255, 0) if person_detected else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f'Person: {confidence:.2f}', 
                   (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, color, 2)
    
    # Добавляем общую информацию
    status = "CASHIER PRESENT" if person_detected else "CASHIER ABSENT"
    status_color = (0, 255, 0) if person_detected else (0, 0, 255)
    
    cv2.putText(frame, f'Status: {status}', (10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
    
    # Информация о времени отсутствия
    if is_absent:
        cv2.putText(frame, f'Absence: {absence_minutes} min', (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    # Информация о таймере
    if timeout_remaining > 0:
        cv2.putText(frame, f'Timeout: {timeout_remaining}s', (10, 100), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
    
    if detection_info:
        max_conf = max(d['confidence'] for d in detection_info)
        cv2.putText(frame, f'Max Conf: {max_conf:.3f}', (10, 130), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return frame
