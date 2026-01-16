import cv2
import numpy as np
from config import CONFIDENCE_THRESHOLD, ROI_LIST

def create_roi_mask(frame_shape, roi_points_list):
    """
    Создает маску для областей интереса (ROI) на основе многоугольников
    """
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    if roi_points_list is not None:
        for roi_points in roi_points_list:
            if roi_points is not None:
                # Преобразуем точки в формат, подходящий для cv2.fillPoly
                pts = np.array(roi_points, dtype=np.int32)
                cv2.fillPoly(mask, [pts], 255)
    return mask

def detect_person(frame, model, confidence_threshold=CONFIDENCE_THRESHOLD, roi_list=None):
    """
    Детекция человека на кадре с порогом уверенности и областями интереса (ROI)
    """
    person_count = 0
    max_confidence = 0.0
    detection_info = []
    
    # Если заданы области интереса, создаем объединенную маску
    if roi_list is not None:
        mask = create_roi_mask(frame.shape, roi_list)
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
                    
                    # Определяем, в какой ROI находится обнаружение
                    roi_index = None
                    if roi_list is not None:
                        for i, roi_points in enumerate(roi_list):
                            if roi_points is not None:
                                # Проверяем центр bounding box
                                center_x = (x1_box + x2_box) // 2
                                center_y = (y1_box + y2_box) // 2
                                
                                # Создаем контур ROI и проверяем точку
                                roi_contour = np.array(roi_points, dtype=np.int32)
                                if cv2.pointPolygonTest(roi_contour, (center_x, center_y), False) >= 0:
                                    roi_index = i + 1  # Нумерация с 1 для удобства
                                    break
                    
                    # Сохраняем информацию о детекции для отрисовки
                    detection_info.append({
                        'bbox': (x1_box, y1_box, x2_box, y2_box),
                        'confidence': confidence,
                        'roi_index': roi_index
                    })
    
    return person_count > 0, max_confidence, detection_info

def detect_person_in_specific_roi(frame, model, roi_index, confidence_threshold=CONFIDENCE_THRESHOLD, roi_list=None):
    """
    Детекция человека в конкретной ROI
    """
    if roi_list is None or roi_index >= len(roi_list) or roi_list[roi_index] is None:
        return False, 0.0, []
    
    # Создаем маску только для указанной ROI
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    roi_points = roi_list[roi_index]
    pts = np.array(roi_points, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    
    # Применяем маску к кадру
    masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
    results = model(masked_frame, verbose=False)
    
    person_detected = False
    max_confidence = 0.0
    detection_info = []
    
    for result in results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                confidence = box.conf[0].item()
                
                if cls == 0 and confidence >= confidence_threshold:
                    person_detected = True
                    max_confidence = max(max_confidence, confidence)
                    
                    # Получаем координаты bounding box
                    x1_box, y1_box, x2_box, y2_box = map(int, box.xyxy[0])
                    
                    # Сохраняем информацию о детекции
                    detection_info.append({
                        'bbox': (x1_box, y1_box, x2_box, y2_box),
                        'confidence': confidence,
                        'roi_index': roi_index + 1
                    })
    
    return person_detected, max_confidence, detection_info

def draw_detections(frame, detection_info, person_detected, roi_list=None, absence_minutes=0, timeout_remaining=0, is_absent=False):
    """
    Отрисовка bounding boxes, информации на кадре и областей интереса (ROI)
    """
    # Рисуем области интереса (ROI) если заданы
    if roi_list is not None:
        colors = [(255, 255, 0), (0, 255, 255)]  # Голубой и желтый для разных ROI
        for i, roi_points in enumerate(roi_list):
            if roi_points is not None:
                color = colors[i % len(colors)]  # Циклическое использование цветов
                # Преобразуем точки в формат, подходящий для cv2.polylines
                pts = np.array(roi_points, dtype=np.int32)
                cv2.polylines(frame, [pts], True, color, 2)
                # Подписываем ROI с указанием назначения
                roi_label = f'ROI {i+1} (casir)' if i == 0 else f'ROI {i+1} (client)'
                cv2.putText(frame, roi_label, (roi_points[0][0], roi_points[0][1]-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    # Рисуем bounding boxes
    for detection in detection_info:
        x1, y1, x2, y2 = detection['bbox']
        confidence = detection['confidence']
        roi_index = detection['roi_index']
        
        color = (0, 255, 0) if person_detected else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Добавляем информацию о ROI к подписи
        roi_text = f" ROI{roi_index}" if roi_index else ""
        cv2.putText(frame, f'Person: {confidence:.2f}{roi_text}', 
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
    
    # УДАЛЕНЫ: Строки с Max Conf и Active ROIs
    
    return frame
