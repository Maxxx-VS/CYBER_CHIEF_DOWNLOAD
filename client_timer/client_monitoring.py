import cv2
import time
import os
import shutil
import numpy as np
from ultralytics import YOLO

from config import (
    RTSP_URL, MODEL_PATH, ROI_LIST, 
    CONFIDENCE_THRESHOLD_CLIENT, SHOW_DETECTION_CLIENT, CAPTURE_INTERVAL_CLIENT,
    CLIENT_APPEARANCE_TIMER, CLIENT_DEPARTURE_TIMER, CASHIER_WAIT_TIMER
)
from database import get_trading_point_schedule, save_client_presence_to_db, sync_offline_data
from video_stream import VideoStream
from detection import detect_person_in_specific_roi, draw_detections
from utils import setup_ram_disk, get_next_state_delay

def run_detection_session(duration, model, ram_disk_path):
    """
    Запускает логику мониторинга на duration секунд.
    """
    print(f"[{time.strftime('%H:%M:%S')}] Начало рабочей смены. Длительность: {duration/3600:.2f} ч.")
    
    # Запуск стрима только на рабочее время
    video_stream = VideoStream(RTSP_URL).start()
    time.sleep(2.0) # Разогрев
    
    session_end_time = time.time() + duration
    
    # Переменные состояния
    client_present = False
    client_appearance_start = None
    client_confirmed_appearance_time = None
    cashier_check_start = None
    
    client_appearance_timer_start = None
    client_departure_timer_start = None
    
    try:
        while time.time() < session_end_time:
            iteration_start = time.time()
            current_time = time.time()
            
            # Чтение кадра
            ret, frame = video_stream.read()
            if not ret:
                if SHOW_DETECTION_CLIENT:
                    error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(error_frame, 'VIDEO STREAM DISCONNECTED', (50, 240), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.imshow('Client Monitoring', error_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): 
                        return False
                time.sleep(CAPTURE_INTERVAL_CLIENT)
                continue
            
            # Сохранение фото
            photo_path = os.path.join(ram_disk_path, f"client_{int(current_time)}.jpg")
            cv2.imwrite(photo_path, frame)
            
            # Детекция
            client_detected, _, client_info = detect_person_in_specific_roi(
                frame, model, 1, CONFIDENCE_THRESHOLD_CLIENT, ROI_LIST
            )
            cashier_detected, _, cashier_info = detect_person_in_specific_roi(
                frame, model, 0, CONFIDENCE_THRESHOLD_CLIENT, ROI_LIST
            )
            
            # --- ЛОГИКА ОТСЛЕЖИВАНИЯ ---
            if client_detected:
                if not client_present:
                    if client_appearance_timer_start is None:
                        client_appearance_timer_start = current_time
                        # [LOG REMOVED] "Обнаружен клиент, таймер..."
                    elif current_time - client_appearance_timer_start >= CLIENT_APPEARANCE_TIMER:
                        client_present = True
                        client_confirmed_appearance_time = current_time
                        client_appearance_start = client_appearance_timer_start
                        client_appearance_timer_start = None
                        cashier_check_start = current_time
                        # [LOG REMOVED] "Клиент подтвержден"
                client_departure_timer_start = None
                
            else: # Клиент не обнаружен
                if client_present:
                    if client_departure_timer_start is None:
                        client_departure_timer_start = current_time
                    elif current_time - client_departure_timer_start >= CLIENT_DEPARTURE_TIMER:
                        # Уход подтвержден
                        departure_time = current_time
                        
                        # Проверка отсутствия кассира во время присутствия клиента
                        if (cashier_check_start is not None and 
                            current_time - cashier_check_start >= CASHIER_WAIT_TIMER and
                            not cashier_detected):
                            
                            wait_minutes = int((departure_time - client_confirmed_appearance_time) // 60)
                            if wait_minutes > 0:
                                save_client_presence_to_db(client_confirmed_appearance_time, departure_time, wait_minutes)
                        
                        client_present = False
                        client_confirmed_appearance_time = None
                        client_departure_timer_start = None
                        cashier_check_start = None
                        # [LOG REMOVED] "Уход клиента подтвержден"
                else:
                    client_appearance_timer_start = None
            # -----------------------------------------------

            # Визуализация
            if SHOW_DETECTION_CLIENT:
                all_detections = client_info + cashier_info
                
                app_rem = 0
                dep_rem = 0
                cash_rem = 0
                
                if client_appearance_timer_start and not client_present:
                    app_rem = max(0, int(CLIENT_APPEARANCE_TIMER - (current_time - client_appearance_timer_start)))
                if client_departure_timer_start and client_present:
                    dep_rem = max(0, int(CLIENT_DEPARTURE_TIMER - (current_time - client_departure_timer_start)))
                if cashier_check_start and client_present and not cashier_detected:
                    cash_rem = max(0, int(CASHIER_WAIT_TIMER - (current_time - cashier_check_start)))
                
                debug_frame = draw_detections(
                    frame.copy(), all_detections, (client_detected or cashier_detected), 
                    ROI_LIST, 0, app_rem, False
                )
                
                status_color = (0, 255, 0) if client_present else (0, 0, 255)
                cv2.putText(debug_frame, f'Client: {"PRESENT" if client_present else "ABSENT"}', (10, 190), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                
                # Доп. инфо
                if app_rem > 0: cv2.putText(debug_frame, f'App timer: {app_rem}s', (10, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                if dep_rem > 0: cv2.putText(debug_frame, f'Dep timer: {dep_rem}s', (10, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                if cash_rem > 0: cv2.putText(debug_frame, f'Cashier wait: {cash_rem}s', (10, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

                # Время до конца сессии
                secs_left = int(session_end_time - current_time)
                cv2.putText(debug_frame, f'Session ends in: {secs_left//60}m {secs_left%60}s', (10, 310), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow('Client Monitoring', debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    return False

            # Очистка RAM
            try: os.remove(photo_path)
            except OSError: pass

            # Пауза
            sleep_time = max(0, CAPTURE_INTERVAL_CLIENT - (time.time() - iteration_start))
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"Ошибка в сессии мониторинга: {e}")
    finally:
        # Фиксация данных при завершении сессии
        if client_present and client_confirmed_appearance_time:
            current_time = time.time()
            if cashier_check_start and (current_time - cashier_check_start >= CASHIER_WAIT_TIMER):
                 wait_minutes = int((current_time - client_confirmed_appearance_time) // 60)
                 if wait_minutes > 0:
                    save_client_presence_to_db(client_confirmed_appearance_time, current_time, wait_minutes)
        
        video_stream.release()
        if SHOW_DETECTION_CLIENT: cv2.destroyAllWindows()
    
    return True

def monitor_client_presence():
    """
    Главный цикл управления состоянием приложения
    """
    ram_disk_path = setup_ram_disk()
    
    try:
        model = YOLO(MODEL_PATH, task='detect')
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    print("Запуск мониторинга наличия клиентов (Smart Schedule)...")
    # [LOG REMOVED] ROI debug info

    try:
        while True:
            # 1. Синхронизация оффлайн данных
            sync_offline_data()
            
            # 2. Получение расписания
            schedule_loaded = False
            while not schedule_loaded:
                schedule_loaded = get_trading_point_schedule()
                if not schedule_loaded:
                    print("Нет связи с БД. Ожидание расписания 60 сек...")
                    time.sleep(60)

            # 3. Расчет состояния
            state, delay = get_next_state_delay()
            
            if state == 'WORK':
                # Запускаем сессию
                run_detection_session(delay, model, ram_disk_path)
            else:
                # Спим до начала смены
                print(f"[{time.strftime('%H:%M:%S')}] Нерабочее время. Сон {delay/3600:.2f} ч.")
                time.sleep(delay)
                # [LOG REMOVED] "Пробуждение..."
                
    except KeyboardInterrupt:
        print("\nОстановка пользователем")
    finally:
        try: shutil.rmtree(ram_disk_path)
        except: pass

if __name__ == "__main__":
    monitor_client_presence()
