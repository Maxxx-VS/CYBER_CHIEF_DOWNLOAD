import cv2
import time
import os
import shutil
import numpy as np
from ultralytics import YOLO

import config
from database import get_trading_point_schedule, save_absence_to_db, sync_offline_data
from video_stream import VideoStream
from detection import detect_person, draw_detections
from utils import setup_ram_disk, get_next_state_delay

def run_detection_session(duration, model, ram_disk_path):
    """
    Запускает цикл детекции на определенное время (duration секунд).
    Возвращает True, если сессия завершилась по времени, False если была прервана ошибкой.
    """
    print(f"[{time.strftime('%H:%M:%S')}] Начало рабочей сессии на {duration/60:.1f} минут.")
    
    # Запуск видеопотока только на время работы
    video_stream = VideoStream(config.RTSP_URL).start()
    time.sleep(2.0) # Разогрев
    
    session_end_time = time.time() + duration
    
    current_absence_start = None
    timeout_start = None
    is_absent = False
    
    try:
        while time.time() < session_end_time:
            iteration_start = time.time()
            current_time = time.time()
            
            # Чтение кадра
            ret, frame = video_stream.read()
            if not ret:
                print("Потеря связи с камерой, ожидание...")
                time.sleep(5)
                continue
            
            # Сохранение на RAM-диск
            photo_path = os.path.join(ram_disk_path, f"cashier_{int(time.time())}.jpg")
            cv2.imwrite(photo_path, frame)
            
            # Детекция
            person_detected, max_confidence, detection_info = detect_person(
                frame, model, config.CONFIDENCE_THRESHOLD, config.ROI
            )
            
            # Логика отсутствия (без изменений)
            if person_detected:
                if is_absent:
                    absence_minutes = int((current_time - current_absence_start) // 60)
                    if absence_minutes > 0:
                        save_absence_to_db(current_absence_start, current_time, absence_minutes)
                    print(f"[{time.strftime('%H:%M:%S')}] Кассир вернулся")
                    is_absent = False
                    current_absence_start = None
                timeout_start = None
            else:
                if not is_absent:
                    if timeout_start is None:
                        timeout_start = current_time
                    elif (current_time - timeout_start) >= config.TIMEOUT_DURATION:
                        is_absent = True
                        current_absence_start = current_time
                        print(f"[{time.strftime('%H:%M:%S')}] Зафиксировано отсутствие")

            # Визуализация (Debug)
            if config.SHOW_DETECTION:
                timeout_remaining = 0
                if timeout_start and not is_absent:
                    timeout_remaining = max(0, int(config.TIMEOUT_DURATION - (current_time - timeout_start)))
                abs_mins = int((current_time - current_absence_start) // 60) if is_absent else 0
                
                debug_frame = draw_detections(
                    frame.copy(), detection_info, person_detected, config.ROI,
                    abs_mins, timeout_remaining, is_absent
                )
                cv2.imshow('Cashier Detection Debug', debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    return False

            # Очистка RAM диска
            try: os.remove(photo_path)
            except: pass
            
            # Подстройка FPS
            sleep_time = max(0, config.CAPTURE_INTERVAL - (time.time() - iteration_start))
            if sleep_time > 0: time.sleep(sleep_time)

    except KeyboardInterrupt:
        raise # Пробрасываем выше
    except Exception as e:
        print(f"Ошибка в сессии детекции: {e}")
    finally:
        # При завершении сессии (конец дня или ошибка) фиксируем текущее отсутствие
        if is_absent and current_absence_start:
            mins = int((time.time() - current_absence_start) // 60)
            if mins > 0:
                save_absence_to_db(current_absence_start, time.time(), mins)
        
        video_stream.release()
        if config.SHOW_DETECTION: cv2.destroyAllWindows()
        
    return True

def monitor_cashier_absence():
    """
    Главный цикл управления состоянием приложения
    """
    ram_disk_path = setup_ram_disk()
    
    # Инициализация модели (один раз)
    try:
        model = YOLO(config.MODEL_PATH, task='detect')
        model.overrides['device'] = 'cpu'
    except Exception as e:
        print(f"Ошибка загрузки YOLO, пробуем fallback: {e}")
        model = YOLO(config.MODEL_PATH, task='detect')

    # Linux fix
    os.environ['QT_QPA_PLATFORM'] = 'xcb'

    print("Система мониторинга запущена.")

    try:
        while True:
            # 1. Попытка синхронизации данных (если интернет появился)
            sync_offline_data()

            # 2. Получение расписания
            # Если нет интернета, get_trading_point_schedule вернет False
            # Мы будем пытаться получить его, пока не получится, с паузой
            schedule_loaded = False
            while not schedule_loaded:
                schedule_loaded = get_trading_point_schedule()
                if not schedule_loaded:
                    print("Нет связи с БД для получения расписания. Повтор через 60 сек...")
                    time.sleep(60)
            
            # 3. Расчет действий
            state, delay_seconds = get_next_state_delay()
            
            if state == 'WORK':
                # Работаем рассчитанное время
                run_detection_session(delay_seconds, model, ram_disk_path)
            else:
                # Спим до начала смены
                print(f"[{time.strftime('%H:%M:%S')}] Нерабочее время. Ожидание {delay_seconds/3600:.2f} часов до начала смены.")
                time.sleep(delay_seconds)
                print("Пробуждение...")

    except KeyboardInterrupt:
        print("\nОстановка пользователем")
    finally:
        try: shutil.rmtree(ram_disk_path)
        except: pass

if __name__ == "__main__":
    monitor_cashier_absence()
