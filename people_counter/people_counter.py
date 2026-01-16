import cv2
import time
import numpy as np
import ast
from ultralytics import YOLO
from config import *
from video_stream import VideoStream
from detection_processor import DetectionProcessor
import schedule_checker
from database import init_local_db, sync_offline_data

def run_ncnn_realtime():
    """
    Реализация инференса в реальном времени с трекингом людей.
    Работает по расписанию с поддержкой оффлайн режима.
    """
    
    # Инициализация локальной базы данных для буферизации
    init_local_db()
    
    # Получаем настройки ROI
    roi_points = None
    try:
        if ROI_STR:
            roi_points = ast.literal_eval(ROI_STR)
            if not isinstance(roi_points, list) or len(roi_points) < 3:
                print("Предупреждение: Некорректный формат ROI. Используется вся область.")
                roi_points = None
            else:
                print(f"ROI активны: True") 
    except Exception as e:
        print(f"Ошибка парсинга ROI: {e}. Используется вся область.")
        roi_points = None

    # Основной цикл приложения
    while True:
        try:
            # 1. Попытка синхронизации данных при старте цикла (если появился интернет)
            sync_offline_data()

            # 2. Получение расписания
            # Если интернета нет, get_trading_point_schedule вернет False
            # Мы будем пытаться получить расписание в цикле, пока не появится связь
            print("Синхронизация расписания...")
            schedule_success = schedule_checker.get_trading_point_schedule()
            
            while not schedule_success:
                print("Нет связи с БД для получения расписания. Ожидание 60 сек...")
                time.sleep(60)
                # Пробуем снова
                schedule_success = schedule_checker.get_trading_point_schedule()

            # 3. Расчет времени (Таймер)
            seconds_to_change, next_is_work = schedule_checker.calculate_next_change_time()
            
            # --- ЛОГИКА НЕРАБОЧЕГО ВРЕМЕНИ ---
            if next_is_work:
                # Мы спим ровно рассчитанное время. Никаких лишних проверок.
                current_time_str = time.strftime("%H:%M:%S")
                print(f"[{current_time_str}] Не рабочие часы. Сон {int(seconds_to_change)} секунд.")
                
                if SHOW_WINDOW:
                    cv2.destroyAllWindows()
                
                # Блокирующий сон до начала смены
                time.sleep(seconds_to_change)
                continue

            # --- ЛОГИКА РАБОЧЕГО ВРЕМЕНИ ---
            else:
                print(f"Рабочая смена. Запуск мониторинга на {int(seconds_to_change)} секунд.")
                
                print(f"Loading model: {MODEL_PATH}...")
                try:
                    model = YOLO(MODEL_PATH, task='detect')
                except Exception as e:
                    print(f"Критическая ошибка загрузки модели: {e}")
                    time.sleep(60)
                    continue
                
                video_stream = VideoStream().start()
                detection_processor = DetectionProcessor(model, roi_points=roi_points).start()
                
                time.sleep(2.0)  # Разогрев камеры
                
                # Работаем ровно до конца смены
                start_loop_time = time.time()
                end_loop_time = start_loop_time + seconds_to_change
                
                last_detection_time = 0
                detection_interval = 1.0 / TARGET_DETECTION_FPS
                
                try:
                    while time.time() < end_loop_time:
                        
                        ret, frame = video_stream.read()
                        
                        if not ret or frame is None:
                            if SHOW_WINDOW:
                                error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                                cv2.putText(error_frame, 'NO SIGNAL', (200, 240), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                                cv2.imshow('Person Detection', error_frame)
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    raise KeyboardInterrupt
                            time.sleep(0.1)
                            continue

                        current_time = time.time()
                        
                        # Отправка на детекцию (FPS limit)
                        if current_time - last_detection_time >= detection_interval:
                            last_detection_time = current_time
                            detection_processor.add_frame(frame)

                        # Визуализация (если включена)
                        if SHOW_WINDOW:
                            display_frame = frame.copy()
                            
                            # Отрисовка ROI
                            if roi_points is not None:
                                roi_array = np.array(roi_points, np.int32)
                                cv2.polylines(display_frame, [roi_array], True, (255, 0, 0), 2)

                            results = detection_processor.get_results()
                            
                            for box, track_id in results['boxes']:
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(display_frame, f'ID: {track_id}', (x1, y1-10), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                            cv2.putText(display_frame, f'Persons: {results["person_count"]}', (10, 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                            
                            rem_time = int(end_loop_time - current_time)
                            cv2.putText(display_frame, f'End shift: {rem_time}s', (10, 60), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

                            cv2.imshow('Person Detection', display_frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                raise KeyboardInterrupt

                    print("Смена окончена. Переход в режим сна.")

                except KeyboardInterrupt:
                    raise 

                except Exception as e:
                    print(f"Ошибка в цикле видео: {e}")
                
                finally:
                    detection_processor.stop()
                    video_stream.release()
                    if SHOW_WINDOW:
                        cv2.destroyAllWindows()
                    del model
                    
        except KeyboardInterrupt:
            print("\nОстановка пользователем")
            break
            
        except Exception as e:
            print(f"Глобальная ошибка: {e}")
            print("Перезапуск через 10 секунд...")
            time.sleep(10)

if __name__ == "__main__":
    run_ncnn_realtime()
