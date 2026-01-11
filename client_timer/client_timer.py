import cv2
import time
import os
import shutil
import numpy as np
from ultralytics import YOLO

# Импорт конфигурации
from config import (
    RTSP_URL, CONFIDENCE_THRESHOLD, SHOW_DETECTION, CAPTURE_INTERVAL,
    TIMEOUT_DURATION, ROI_LIST, MODEL_PATH, WORK_SCHEDULE
)
import config 

# Обновленные импорты из utils и database, как в client_monitoring.py
from database import get_trading_point_schedule, save_absence_to_db, sync_offline_data
from video_stream import VideoStream
from detection import detect_person, draw_detections
from utils import setup_ram_disk, get_next_state_delay

def run_cashier_session(duration, model, ram_disk_path):
    """
    Сессия мониторинга кассира на рабочее время (duration секунд).
    """
    print(f"[{time.strftime('%H:%M:%S')}] Рабочая смена. Запуск мониторинга на {duration:.0f} секунд.")
    
    # Запускаем поток видео только на время смены
    video_stream = VideoStream(RTSP_URL).start()
    time.sleep(2.0) # Разогрев камеры
    
    session_end_time = time.time() + duration
    
    # Переменные состояния (локальные для сессии)
    current_absence_start = None
    timeout_start = None
    is_absent = False
    
    try:
        while time.time() < session_end_time:
            loop_start = time.time()
            
            # Чтение кадра
            ret, frame = video_stream.read()
            if not ret:
                if SHOW_DETECTION:
                    pass
                time.sleep(CAPTURE_INTERVAL)
                continue
            
            # Сохранение фото (для обработки)
            photo_path = os.path.join(ram_disk_path, f"cashier_{int(loop_start)}.jpg")
            cv2.imwrite(photo_path, frame)
            
            # Детекция
            person_detected, max_conf, detection_info = detect_person(
                frame, model, CONFIDENCE_THRESHOLD, ROI_LIST
            )
            
            # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ОТСУТСТВИЯ ---
            if person_detected:
                if is_absent:
                    # Кассир вернулся
                    absence_min = int((loop_start - current_absence_start) // 60)
                    if absence_min > 0:
                        save_absence_to_db(current_absence_start, loop_start, absence_min)
                    # [LOG REMOVED] Operational noise
                    is_absent = False
                    current_absence_start = None
                timeout_start = None
            else:
                # Кассира нет
                if not is_absent:
                    if timeout_start is None:
                        timeout_start = loop_start
                    elif loop_start - timeout_start >= TIMEOUT_DURATION:
                        is_absent = True
                        current_absence_start = loop_start
                        # [LOG REMOVED] Operational noise
            
            # Отрисовка
            if SHOW_DETECTION:
                to_rem = max(0, int(TIMEOUT_DURATION - (loop_start - timeout_start))) if timeout_start and not is_absent else 0
                abs_min = int((loop_start - current_absence_start) // 60) if is_absent else 0
                
                # Рисуем
                debug_frame = draw_detections(frame.copy(), detection_info, person_detected, ROI_LIST, abs_min, to_rem, is_absent)
                
                # Добавляем инфо о времени до конца смены
                secs_left = int(session_end_time - time.time())
                cv2.putText(debug_frame, f'End shift in: {secs_left//3600}h {(secs_left%3600)//60}m', 
                           (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                cv2.imshow('Cashier Detection', debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    return False

            # Удаление временного файла
            try:
                os.remove(photo_path)
            except OSError: pass
            
            # Умная пауза
            processing_time = time.time() - loop_start
            sleep_time = max(0, CAPTURE_INTERVAL - processing_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"Ошибка в сессии кассира: {e}")
    finally:
        # При завершении сессии (конец дня) закрываем незавершенные отсутствия
        if is_absent and current_absence_start:
             absence_min = int((time.time() - current_absence_start) // 60)
             if absence_min > 0:
                save_absence_to_db(current_absence_start, time.time(), absence_min)
        
        video_stream.release()
        if SHOW_DETECTION: cv2.destroyAllWindows()
    
    return True

def monitor_cashier_absence():
    """
    Главный цикл управления состоянием
    """
    ram_disk_path = setup_ram_disk()
    
    # Загружаем модель один раз
    try:
        model = YOLO(MODEL_PATH, task='detect')
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    print("Инициализация сервиса мониторинга кассира...")

    try:
        while True:
            # 1. Синхронизация данных
            sync_offline_data()
            
            # 2. Получение/Обновление расписания
            # [LOG REMOVED] "Синхронизация расписания..."
            schedule_loaded = False
            while not schedule_loaded:
                schedule_loaded = get_trading_point_schedule()
                if not schedule_loaded:
                    print("Нет связи с БД. Повтор через 60 сек...")
                    time.sleep(60)
            
            # Вывод расписания только при старте или изменении можно было бы оставить, 
            # но для минимизации оставим только при явном обновлении, если нужно.
            # В данном цикле он обновляется каждую итерацию (сутки/смена), поэтому лог полезен для отладки старта смены.
            # Оставляем только важный статус.
            if WORK_SCHEDULE['start_time'] and WORK_SCHEDULE['end_time']:
                 # Можно закомментировать, если этот лог слишком частый (раз в смену - приемлемо)
                 pass 

            # 3. Расчет состояния (WORK или SLEEP)
            state, delay = get_next_state_delay()
            
            if state == 'WORK':
                # Запуск рабочей сессии
                run_cashier_session(delay, model, ram_disk_path)
                print("Смена окончена. Переход в режим ожидания.")
            else:
                # Режим сна
                print(f"[{time.strftime('%H:%M:%S')}] Не рабочие часы. Сон {delay:.0f} секунд.")
                
                # Закрываем окна OpenCV на ночь
                if SHOW_DETECTION:
                    cv2.destroyAllWindows()
                    
                time.sleep(delay)
                # [LOG REMOVED] "Пробуждение..."

    except KeyboardInterrupt:
        print("\nОстановка пользователем")
    finally:
        try: shutil.rmtree(ram_disk_path)
        except: pass

if __name__ == "__main__":
    monitor_cashier_absence()
