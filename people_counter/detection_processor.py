# detection_processor.py

import time
import threading
import cv2
import numpy as np
from collections import deque
from ultralytics import YOLO
from config import REPORT_INTERVAL, CONFIDENCE_THRESHOLD
from database import save_people_count_to_db

class DetectionProcessor:
    """
    Класс для обработки детекции и трекинга в отдельном потоке
    """
    def __init__(self, model, roi_points=None, report_interval=None):
        self.model = model
        self.roi_points = roi_points
        self.lock = threading.Lock()
        self.current_results = {
            'person_count': 0,
            'tracked_people': set(),  # Множество для отслеживания уникальных ID людей
            'boxes': [],
            'timestamp': 0,
            'processed_frames': 0
        }
        self.frame_queue = deque(maxlen=1)  # Очередь на 1 кадр
        self.stopped = False
        self.processing = False
        
        # Получаем интервал отчета из переменных окружения
        self.report_interval = report_interval or REPORT_INTERVAL
        
        # Статистика для периодического вывода и сохранения в БД
        self.last_report_time = time.time()
        self.all_tracked_people = set()  # Все уникальные люди за период
        
    def start(self):
        """Запуск потока обработки"""
        self.thread = threading.Thread(target=self.process, args=())
        self.thread.daemon = True
        self.thread.start()
        return self
        
    def add_frame(self, frame):
        """Добавление кадра для обработки"""
        if not self.processing and frame is not None:
            self.frame_queue.append(frame)
            
    def is_point_in_roi(self, x, y):
        """Проверяет, находится ли точка внутри ROI"""
        if self.roi_points is None or len(self.roi_points) < 3:
            return True  # Если ROI не задан, считаем всю область валидной
        
        # Преобразуем точки ROI в numpy массив
        roi_array = np.array(self.roi_points, np.int32)
        
        # Используем pointPolygonTest для проверки нахождения точки внутри полигона
        result = cv2.pointPolygonTest(roi_array, (x, y), False)
        return result >= 0  # >=0 означает внутри полигона, <0 - снаружи
    
    def process(self):
        """Основной цикл обработки"""
        while not self.stopped:
            if self.frame_queue:
                frame = self.frame_queue[0]
                self.processing = True
                
                try:
                    # Выполняем детекцию с трекингом
                    results = self.model.track(frame, persist=True, verbose=False, conf=CONFIDENCE_THRESHOLD)
                    
                    # Обрабатываем результаты
                    person_count = 0
                    current_tracked_people = set()
                    boxes = []
                    
                    for result in results:
                        result_boxes = result.boxes
                        if result_boxes is not None and result_boxes.id is not None:
                            for box, track_id in zip(result_boxes, result_boxes.id):
                                cls = int(box.cls[0])
                                confidence = box.conf[0].item()
                                
                                # Фильтруем только людей с достаточной уверенностью
                                if cls == 0 and confidence >= CONFIDENCE_THRESHOLD:
                                    # Получаем координаты bounding box
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    
                                    # Проверяем, находится ли центр нижней части bounding box внутри ROI
                                    center_x = (x1 + x2) // 2
                                    center_y = y2  # Нижний центр bounding box
                                    
                                    if self.is_point_in_roi(center_x, center_y):
                                        person_count += 1
                                        track_id_int = int(track_id.item())
                                        current_tracked_people.add(track_id_int)
                                        self.all_tracked_people.add(track_id_int)
                                        boxes.append((box, track_id_int))
                    
                    # Проверяем, нужно ли вывести отчет и сохранить в БД
                    current_time = time.time()
                    if current_time - self.last_report_time >= self.report_interval:
                        unique_people_count = len(self.all_tracked_people)
                        
                        # Сохраняем в БД
                        save_people_count_to_db(unique_people_count)
                        
                        # Убрали дублирующий вывод в консоль
                        # print(f"За последние {self.report_interval/60} минут обнаружено {unique_people_count} уникальных людей")
                        
                        # Сбрасываем ВСЕ счетчики ID (важное изменение!)
                        self.all_tracked_people.clear()
                        # Также сбрасываем текущие tracked_people чтобы начать новый период с чистого листа
                        with self.lock:
                            self.current_results['tracked_people'].clear()
                        
                        self.last_report_time = current_time
                    
                    # Обновляем результаты
                    with self.lock:
                        self.current_results = {
                            'person_count': person_count,
                            'tracked_people': current_tracked_people,
                            'boxes': boxes,
                            'timestamp': current_time,
                            'processed_frames': self.current_results['processed_frames'] + 1
                        }
                    
                    # Удаляем обработанный кадр
                    if self.frame_queue:
                        self.frame_queue.pop()
                        
                except Exception as e:
                    print(f"Ошибка при обработке детекции: {e}")
                
                self.processing = False
            else:
                time.sleep(0.001)  # Короткая пауза если нет кадров для обработки
                
    def get_results(self):
        """Получение текущих результатов"""
        with self.lock:
            return self.current_results.copy()
            
    def stop(self):
        """Остановка потока"""
        self.stopped = True
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
