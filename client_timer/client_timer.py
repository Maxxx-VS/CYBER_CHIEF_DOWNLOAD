import cv2
import time
import os
import shutil
import numpy as np
import threading
from ultralytics import YOLO

# Импорт конфигурации
from config import (
    RTSP_URL, 
    # Настройки кассира
    CONFIDENCE_THRESHOLD_CASSIR, SHOW_DETECTION_CASSIR, CAPTURE_INTERVAL_CASSIR,
    TIMEOUT_DURATION_CASSIR, ROI_LIST, MODEL_PATH,
    # Настройки клиента
    CONFIDENCE_THRESHOLD_CLIENT, SHOW_DETECTION_CLIENT, CAPTURE_INTERVAL_CLIENT,
    CLIENT_APPEARANCE_TIMER, CLIENT_DEPARTURE_TIMER, CASHIER_WAIT_TIMER
)

# Импорты из других модулей
from database import get_trading_point_schedule, save_absence_to_db, save_client_presence_to_db, sync_offline_data
from video_stream import VideoStream
from detection import detect_person_in_specific_roi, draw_detections
from utils import setup_ram_disk, get_next_state_delay

def run_cashier_session(duration, model, ram_disk_path):
    """
    Сессия мониторинга кассира на рабочее время (duration секунд).
    """
    print(f"[{time.strftime('%H:%M:%S')}] [КАССИР] Запуск мониторинга на {duration/3600:.2f} ч.")
    
    # Запускаем поток видео только на время смены
    video_stream = VideoStream(RTSP_URL).start()
    time.sleep(2.0)  # Разогрев камеры
    
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
                time.sleep(CAPTURE_INTERVAL_CASSIR)
                continue
            
            # Сохранение фото (для обработки)
            photo_path = os.path.join(ram_disk_path, f"cashier_{int(loop_start)}.jpg")
            cv2.imwrite(photo_path, frame)
            
            # Детекция кассира (ROI 0 - кассир)
            person_detected, max_conf, detection_info = detect_person_in_specific_roi(
                frame, model, 0, CONFIDENCE_THRESHOLD_CASSIR, ROI_LIST
            )
            
            # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ОТСУТСТВИЯ КАССИРА ---
            if person_detected:
                if is_absent:
                    # Кассир вернулся
                    absence_min = int((loop_start - current_absence_start) // 60)
                    if absence_min > 0:
                        save_absence_to_db(current_absence_start, loop_start, absence_min)
                    is_absent = False
                    current_absence_start = None
                timeout_start = None
            else:
                # Кассира нет
                if not is_absent:
                    if timeout_start is None:
                        timeout_start = loop_start
                    elif loop_start - timeout_start >= TIMEOUT_DURATION_CASSIR:
                        is_absent = True
                        current_absence_start = loop_start
            
            # Отрисовка (только если включен показ для кассира)
            if SHOW_DETECTION_CASSIR:
                to_rem = max(0, int(TIMEOUT_DURATION_CASSIR - (loop_start - timeout_start))) if timeout_start and not is_absent else 0
                abs_min = int((loop_start - current_absence_start) // 60) if is_absent else 0
                
                # Рисуем детекции
                debug_frame = draw_detections(frame.copy(), detection_info, person_detected, ROI_LIST, abs_min, to_rem, is_absent)
                
                # Добавляем инфо о времени до конца смены
                secs_left = int(session_end_time - time.time())
                cv2.putText(debug_frame, f'End shift in: {secs_left//3600}h {(secs_left%3600)//60}m {secs_left%60}s', 
                           (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                cv2.imshow('Cashier Detection', debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    return False

            # Удаление временного файла
            try:
                os.remove(photo_path)
            except OSError: 
                pass
            
            # Умная пауза
            processing_time = time.time() - loop_start
            sleep_time = max(0, CAPTURE_INTERVAL_CASSIR - processing_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"Ошибка в сессии кассира: {e}")
    finally:
        # При завершении сессии закрываем незавершенные отсутствия
        if is_absent and current_absence_start:
            current_time = time.time()
            absence_min = int((current_time - current_absence_start) // 60)
            if absence_min > 0:
                save_absence_to_db(current_absence_start, current_time, absence_min)
        
        video_stream.release()
        if SHOW_DETECTION_CASSIR: 
            cv2.destroyAllWindows()
    
    return True

def run_client_session(duration, model, ram_disk_path):
    """
    Сессия мониторинга клиентов на рабочее время (duration секунд).
    """
    print(f"[{time.strftime('%H:%M:%S')}] [КЛИЕНТ] Запуск мониторинга на {duration/3600:.2f} ч.")
    
    # Запуск стрима
    video_stream = VideoStream(RTSP_URL).start()
    time.sleep(2.0)  # Разогрев
    
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
            
            # Детекция клиента (ROI 1 - клиент)
            client_detected, _, client_info = detect_person_in_specific_roi(
                frame, model, 1, CONFIDENCE_THRESHOLD_CLIENT, ROI_LIST
            )
            
            # Детекция кассира (ROI 0 - кассир)
            cashier_detected, _, cashier_info = detect_person_in_specific_roi(
                frame, model, 0, CONFIDENCE_THRESHOLD_CLIENT, ROI_LIST
            )
            
            # --- ЛОГИКА ОТСЛЕЖИВАНИЯ КЛИЕНТА ---
            if client_detected:
                if not client_present:
                    if client_appearance_timer_start is None:
                        client_appearance_timer_start = current_time
                    elif current_time - client_appearance_timer_start >= CLIENT_APPEARANCE_TIMER:
                        client_present = True
                        client_confirmed_appearance_time = current_time
                        client_appearance_start = client_appearance_timer_start
                        client_appearance_timer_start = None
                        cashier_check_start = current_time
                client_departure_timer_start = None
                
            else:  # Клиент не обнаружен
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
                else:
                    client_appearance_timer_start = None

            # Визуализация (только если включен показ для клиента)
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
                if app_rem > 0: 
                    cv2.putText(debug_frame, f'App timer: {app_rem}s', (10, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                if dep_rem > 0: 
                    cv2.putText(debug_frame, f'Dep timer: {dep_rem}s', (10, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                if cash_rem > 0: 
                    cv2.putText(debug_frame, f'Cashier wait: {cash_rem}s', (10, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

                # Время до конца сессии
                secs_left = int(session_end_time - current_time)
                cv2.putText(debug_frame, f'Session ends in: {secs_left//60}m {secs_left%60}s', (10, 310), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow('Client Monitoring', debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    return False

            # Очистка RAM
            try: 
                os.remove(photo_path)
            except OSError: 
                pass

            # Пауза
            sleep_time = max(0, CAPTURE_INTERVAL_CLIENT - (time.time() - iteration_start))
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"Ошибка в сессии мониторинга клиента: {e}")
    finally:
        # Фиксация данных при завершении сессии
        if client_present and client_confirmed_appearance_time:
            current_time = time.time()
            if cashier_check_start and (current_time - cashier_check_start >= CASHIER_WAIT_TIMER):
                wait_minutes = int((current_time - client_confirmed_appearance_time) // 60)
                if wait_minutes > 0:
                    save_client_presence_to_db(client_confirmed_appearance_time, current_time, wait_minutes)
        
        video_stream.release()
        if SHOW_DETECTION_CLIENT: 
            cv2.destroyAllWindows()
    
    return True

def start_monitoring_threads(duration, model):
    """
    Запускает оба мониторинга в отдельных потоках
    """
    # Создаем отдельные RAM-диски для каждого потока
    cashier_ram_disk = setup_ram_disk("cashier")
    client_ram_disk = setup_ram_disk("client")
    
    # Событие для остановки потоков
    stop_event = threading.Event()
    
    # Функции для запуска в потоках
    def cashier_monitoring():
        try:
            run_cashier_session(duration, model, cashier_ram_disk)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                shutil.rmtree(cashier_ram_disk, ignore_errors=True)
            except:
                pass
    
    def client_monitoring():
        try:
            run_client_session(duration, model, client_ram_disk)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                shutil.rmtree(client_ram_disk, ignore_errors=True)
            except:
                pass
    
    # Запускаем потоки
    cashier_thread = threading.Thread(target=cashier_monitoring, daemon=True)
    client_thread = threading.Thread(target=client_monitoring, daemon=True)
    
    cashier_thread.start()
    client_thread.start()
    
    return cashier_thread, client_thread

def monitor_system():
    """
    Главный цикл управления состоянием приложения
    """
    # Загружаем модель один раз
    try:
        model = YOLO(MODEL_PATH, task='detect')
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    print("Запуск системы мониторинга (Кассир + Клиенты)...")

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
                # Запускаем оба мониторинга
                print(f"[{time.strftime('%H:%M:%S')}] Начало рабочей смены. Длительность: {delay/3600:.2f} ч.")
                cashier_thread, client_thread = start_monitoring_threads(delay, model)
                
                # Ждем завершения обоих потоков
                cashier_thread.join()
                client_thread.join()
                
                print(f"[{time.strftime('%H:%M:%S')}] Смена окончена.")
            else:
                # Спим до начала смены
                print(f"[{time.strftime('%H:%M:%S')}] Нерабочее время. Сон {delay/3600:.2f} ч.")
                
                # Закрываем окна OpenCV на ночь
                cv2.destroyAllWindows()
                time.sleep(delay)
                
    except KeyboardInterrupt:
        print("\nОстановка пользователем")
    except Exception as e:
        print(f"Критическая ошибка в системе мониторинга: {e}")
    finally:
        # Закрываем все окна OpenCV
        cv2.destroyAllWindows()

if __name__ == "__main__":
    monitor_system()
