import cv2
import numpy as np
import os
import subprocess
import threading
import time
from datetime import datetime
from ultralytics import YOLO
from config import MODEL_PATH, CONFIDENCE_THRESHOLD, ROI, HAT_GLOVE_MODEL_PATH, HAT_GLOVE_CONFIDENCE_THRESHOLD, ROI_TABLE, ID_POINT, RAM_DISK_PATH, COUNT_VIOLATIONS, SOUND_PATH_WARNING
from sftp_client import SFTPUploader

# Импортируем функцию локального сохранения
from database import save_violation_to_local 

HAT_GLOVE_CLASSES = {0: 'hat', 1: 'glove'}

# Глобальный счетчик подряд идущих нарушений
consecutive_violations_count = 0
is_sound_playing = False
sound_lock = threading.Lock()

def is_point_in_polygon(point, polygon):
    """Проверка, находится ли точка внутри полигона"""
    x, y = point
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def bbox_intersects_polygon(bbox, polygon):
    """Проверка пересечения bounding box с полигоном"""
    if polygon is None: 
        return False
    x1, y1, x2, y2 = bbox
    points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), ((x1+x2)//2, (y1+y2)//2)]
    for p in points:
        if is_point_in_polygon(p, polygon): 
            return True
    return False

def get_polygon_bounding_rect(polygon):
    """Получение ограничивающего прямоугольника для полигона"""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (max(0, min(xs)), max(0, min(ys)), min(9999, max(xs)), min(9999, max(ys)))

def detect_person(frame, model, confidence_threshold=CONFIDENCE_THRESHOLD, roi=ROI, roi_table=ROI_TABLE):
    """Детекция людей в кадре"""
    roi_rect = get_polygon_bounding_rect(roi)
    x1_rect, y1_rect, x2_rect, y2_rect = roi_rect
    
    # Проверка границ ROI
    if (x1_rect >= x2_rect or y1_rect >= y2_rect or 
        x2_rect > frame.shape[1] or y2_rect > frame.shape[0]):
        return False, 0.0, [], []
    
    roi_frame = frame[y1_rect:y2_rect, x1_rect:x2_rect]
    
    # Проверка, что ROI не пустой
    if roi_frame.size == 0:
        return False, 0.0, [], []
        
    results = model(roi_frame, verbose=False)
    
    person_count = 0
    max_confidence = 0.0
    detection_info = []
    person_bboxes = []
    
    for result in results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                conf = box.conf[0].item()
                if cls == 0 and conf >= confidence_threshold:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1_f, y1_f = x1 + roi_rect[0], y1 + roi_rect[1]
                    x2_f, y2_f = x2 + roi_rect[0], y2 + roi_rect[1]
                    cx, cy = (x1_f + x2_f)//2, (y1_f + y2_f)//2
                    
                    if is_point_in_polygon((cx, cy), roi):
                        person_count += 1
                        max_confidence = max(max_confidence, conf)
                        bbox = (x1_f, y1_f, x2_f, y2_f)
                        person_bboxes.append(bbox)
                        inter = False
                        if roi_table: 
                            inter = bbox_intersects_polygon(bbox, roi_table)
                        detection_info.append({
                            'bbox': bbox, 
                            'confidence': conf, 
                            'class': 'person', 
                            'intersects_table': inter
                        })
    return person_count > 0, max_confidence, detection_info, person_bboxes

def load_model():
    """Загрузка модели детекции людей"""
    try:
        model = YOLO(MODEL_PATH, task='detect')
        print(f"Model loaded: {MODEL_PATH}")
        return model
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

def load_hat_glove_model():
    """Загрузка модели детекции средств защиты"""
    try:
        model = YOLO(HAT_GLOVE_MODEL_PATH, task='detect')
        print(f"PPE Model loaded: {HAT_GLOVE_MODEL_PATH}")
        return model
    except Exception as e:
        print(f"Error loading PPE model: {e}")
        return None

def detect_hat_glove(frame, model, person_bboxes, confidence_threshold=HAT_GLOVE_CONFIDENCE_THRESHOLD):
    """Детекция шлемов и перчаток"""
    if model is None: 
        return [], []
        
    results = model.predict(frame, conf=confidence_threshold, classes=[0, 1], verbose=False)
    hg_dets = []
    g_dets = []
    
    if results and results[0].boxes is not None:
        for box in results[0].boxes:
            cls = int(box.cls[0])
            conf = box.conf[0].item()
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1+x2)//2, (y1+y2)//2
            
            in_person = False
            for px1, py1, px2, py2 in person_bboxes:
                if px1 <= cx <= px2 and py1 <= cy <= py2:
                    in_person = True
                    break
            if in_person:
                info = {
                    'bbox': (x1, y1, x2, y2), 
                    'confidence': conf, 
                    'class': HAT_GLOVE_CLASSES.get(cls, 'unknown')
                }
                hg_dets.append(info)
                if cls == 1: 
                    g_dets.append(info)
    return hg_dets, g_dets

def check_violation(person_info, glove_detections, frame, timestamp):
    """Проверка нарушений (отсутствие перчаток)"""
    global consecutive_violations_count
    violations = []
    
    # Проверяем каждого человека в ROI_TABLE
    for person in person_info:
        if person.get('intersects_table', False):
            px1, py1, px2, py2 = person['bbox']
            has_glove = False
            
            for glove in glove_detections:
                gx1, gy1, gx2, gy2 = glove['bbox']
                # Проверка пересечения bounding boxes
                if (gx1 < px2 and gx2 > px1 and gy1 < py2 and gy2 > py1):
                    has_glove = True
                    break
                    
            if not has_glove:
                violations.append({
                    'person_bbox': person['bbox'], 
                    'timestamp': timestamp, 
                    'person_confidence': person['confidence']
                })
    
    # Обновление счетчика нарушений
    if violations:
        consecutive_violations_count += 1
        print(f"[Violation] Consecutive: {consecutive_violations_count}/{COUNT_VIOLATIONS}")
    else:
        # Если на этом кадре нет нарушений - сбрасываем счетчик
        consecutive_violations_count = 0
    
    return violations

def play_warning_sound():
    """Воспроизведение звука предупреждения"""
    global is_sound_playing
    
    if not SOUND_PATH_WARNING or not os.path.exists(SOUND_PATH_WARNING):
        print(f"Warning sound file not found: {SOUND_PATH_WARNING}")
        return
    
    with sound_lock:
        if is_sound_playing:
            return
        is_sound_playing = True
    
    def play():
        try:
            subprocess.run(
                ['mpg123', '-q', SOUND_PATH_WARNING],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )
        except subprocess.TimeoutExpired:
            print("Warning sound playback timeout")
        except Exception as e:
            print(f"Error playing warning sound: {e}")
        finally:
            with sound_lock:
                global is_sound_playing
                is_sound_playing = False

    threading.Thread(target=play, daemon=True).start()

def save_violation_images(frame, violations):
    """Сохранение изображений нарушений"""
    global consecutive_violations_count
    
    if consecutive_violations_count >= COUNT_VIOLATIONS:
        print(f"[ATTENTION] Threshold reached ({COUNT_VIOLATIONS}). Saving evidence.")
        
        uploader = SFTPUploader()
        
        # Создание директории RAM диска при необходимости
        if not os.path.exists(RAM_DISK_PATH):
            try: 
                os.makedirs(RAM_DISK_PATH, exist_ok=True)
            except Exception as e:
                print(f"Error creating RAM disk directory: {e}")
                return
        
        if violations:
            violation = violations[0]
            timestamp = violation['timestamp']
            person_bbox = violation['person_bbox']
            
            violation_frame = frame.copy()
            x1, y1, x2, y2 = person_bbox
            
            # Рисуем bounding box нарушителя
            cv2.rectangle(violation_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
            
            # Добавляем текст
            cv2.putText(violation_frame, f'VIOLATION: No gloves ({consecutive_violations_count})', 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            cv2.putText(violation_frame, f'Point ID: {ID_POINT}', 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
            
            dt_object = datetime.fromtimestamp(timestamp)
            filename = f"{ID_POINT}_VIOLATION_{dt_object.strftime('%Y-%m-%d_%H-%M-%S')}.jpeg"
            local_path = os.path.join(RAM_DISK_PATH, filename)
            
            try:
                if cv2.imwrite(local_path, violation_frame):
                    print(f"Violation image saved: {local_path}")
                    
                    # Попытка загрузки на SFTP
                    if not uploader.upload_file(local_path, filename):
                        # Если не удалось загрузить -> сохраняем в оффлайн буфер
                        print("SFTP upload failed. Saving to offline buffer.")
                        save_violation_to_local(local_path, filename)
                    
                    # Воспроизведение звука при достижении порога
                    play_warning_sound()
                    
                    # Сброс счетчика после реакции
                    consecutive_violations_count = 0
                else:
                    print(f"Failed to save image: {local_path}")
            except Exception as e:
                print(f"Error saving violation: {e}")

def draw_detections(frame, person_info, hg_info, person_detected, roi=ROI, roi_table=ROI_TABLE, violations=None):
    """Отрисовка детекций на кадре"""
    # Рисуем ROI
    if roi: 
        cv2.polylines(frame, [np.array(roi, dtype=np.int32)], True, (255,255,0), 2)
    if roi_table: 
        cv2.polylines(frame, [np.array(roi_table, dtype=np.int32)], True, (0,255,255), 2)
    
    # Рисуем bounding boxes людей
    for d in person_info:
        x1, y1, x2, y2 = d['bbox']
        # Красный цвет для нарушителей, зеленый для остальных
        if violations and any(v['person_bbox'] == d['bbox'] for v in violations):
            color = (0, 0, 255)  # Красный
        else:
            color = (0, 255, 0)  # Зеленый
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Добавляем confidence score
        cv2.putText(frame, f"{d['confidence']:.2f}", 
                   (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    # Рисуем bounding boxes средств защиты
    for d in hg_info:
        x1, y1, x2, y2 = d['bbox']
        color = (255, 0, 0)  # Синий для средств защиты
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Добавляем название класса
        cv2.putText(frame, f"{d['class']} {d['confidence']:.2f}", 
                   (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Добавляем счетчик нарушений
    cv2.putText(frame, f"Violations: {consecutive_violations_count}/{COUNT_VIOLATIONS}", 
               (10, 400), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
    
    return frame

def reset_violation_counter():
    """Сбрасывает счетчик последовательных нарушений"""
    global consecutive_violations_count
    consecutive_violations_count = 0
