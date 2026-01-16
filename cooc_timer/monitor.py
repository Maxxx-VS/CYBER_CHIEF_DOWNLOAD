import os
import time
import cv2
import numpy as np
import shutil
from config import SHOW_DETECTION, CAPTURE_INTERVAL, RAM_DISK_PATH, TIMEOUT_DURATION, ROI_TABLE
from database import check_database_connection, save_work_session_to_db, get_gmt_offset
from video_stream import VideoStream
from detection import load_model, load_hat_glove_model, detect_person, detect_hat_glove, draw_detections, check_violation, save_violation_images, reset_violation_counter
from schedule import should_monitoring_be_active
from sftp_client import SFTPUploader

def setup_ram_disk():
    """Настройка RAM-диска"""
    if not os.path.exists(RAM_DISK_PATH):
        os.makedirs(RAM_DISK_PATH)
    else:
        # Очистка только файлов, оставляем директорию
        for filename in os.listdir(RAM_DISK_PATH):
            file_path = os.path.join(RAM_DISK_PATH, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Ошибка при очистке файла {file_path}: {e}")
    return RAM_DISK_PATH

def monitor_chef_work_time():
    """Основной цикл мониторинга"""
    ram_disk_path = setup_ram_disk()
    
    # Проверка БД
    db_connection_ok = check_database_connection()
    if not db_connection_ok:
        print("ВНИМАНИЕ: Проблемы с БД. Данные не будут сохраняться.")
    
    # Проверка SFTP структуры
    sftp_ok = SFTPUploader().ensure_directories()
    if not sftp_ok:
         print("ВНИМАНИЕ: Проблемы с SFTP. Фото нарушений могут не сохраняться.")

    # Первичная инициализация
    get_gmt_offset()
    
    # Загрузка моделей
    model_person = load_model()
    model_hat_glove = load_hat_glove_model()
    
    if model_person is None:
        print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить модель детекции людей!")
        return
    
    video_stream = VideoStream().start()
    time.sleep(2.0) # Разогрев камеры
    
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    print("Запуск мониторинга... Нажмите Ctrl+C для остановки")
    
    work_session_start = None
    is_working = False
    last_detection_time = None
    last_gmt_check = time.time()
    
    try:
        while True:
            iteration_start = time.time()
            
            # Раз в сутки обновляем GMT
            if time.time() - last_gmt_check >= 86400:
                get_gmt_offset()
                last_gmt_check = time.time()
            
            if not should_monitoring_be_active():
                if SHOW_DETECTION:
                    show_status_screen("NON-WORKING HOURS", (0, 165, 255))
                time.sleep(CAPTURE_INTERVAL)
                continue
            
            ret, frame = video_stream.read()
            if not ret:
                if SHOW_DETECTION:
                    show_status_screen("VIDEO STREAM DISCONNECTED", (0, 0, 255))
                time.sleep(CAPTURE_INTERVAL)
                continue
            
            # Работа с RAM диском (сохранение текущего кадра для других целей, если нужно)
            timestamp = int(time.time())
            photo_path = os.path.join(ram_disk_path, f"chef_{timestamp}.jpg")
            cv2.imwrite(photo_path, frame)
            
            # --- Детекция ---
            person_detected, max_conf, person_info, person_bboxes = detect_person(frame, model_person, roi_table=ROI_TABLE)
            
            hat_glove_info, glove_detections = [], []
            if person_detected:
                hat_glove_info, glove_detections = detect_hat_glove(frame, model_hat_glove, person_bboxes)
            
            # Проверка нарушений
            violations = []
            if ROI_TABLE is not None and person_detected:
                violations = check_violation(person_info, glove_detections, frame, timestamp)
                
                # Сохраняем фото нарушения и воспроизводим звук, если достигнут порог
                if violations:
                    save_violation_images(frame, violations)
            else:
                # Если не выполняются условия для проверки нарушений
                # (нет ROI_TABLE или нет людей) - сбрасываем счетчик
                reset_violation_counter()
            
            current_time = time.time()
            
            # Логика сессий
            if person_detected:
                last_detection_time = current_time
                if not is_working:
                    work_session_start = current_time
                    is_working = True
                    print(f"[{time.strftime('%H:%M:%S')}] Начало рабочей сессии")
            
            elif is_working and last_detection_time is not None:
                # Проверка таймаута
                if (current_time - last_detection_time) >= TIMEOUT_DURATION:
                    session_duration = int(last_detection_time - work_session_start)
                    if db_connection_ok:
                        save_work_session_to_db(work_session_start, last_detection_time, session_duration)
                    
                    print(f"[{time.strftime('%H:%M:%S')}] Конец рабочей сессии. Длительность: {session_duration} сек")
                    is_working = False
                    work_session_start = None
                    last_detection_time = None
            
            # --- Визуализация ---
            if SHOW_DETECTION:
                debug_frame = draw_detections(frame.copy(), person_info, hat_glove_info, person_detected, 
                                             roi_table=ROI_TABLE, violations=violations)
                
                # Добавляем информацию о статусе
                status_text = "РАБОТАЕТ" if person_detected else "НЕ РАБОТАЕТ"
                status_color = (0, 255, 0) if person_detected else (0, 0, 255)
                cv2.putText(debug_frame, f"Статус: {status_text}", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                
                if is_working and work_session_start:
                    session_time = int(current_time - work_session_start)
                    cv2.putText(debug_frame, f"Сессия: {session_time} сек", 
                               (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                cv2.imshow('Chef Detection Debug', debug_frame)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    break
            
            # Удаление временного файла
            try:
                os.remove(photo_path)
            except OSError:
                pass
            
            # Соблюдение интервала захвата
            processing_time = time.time() - iteration_start
            sleep_time = max(0, CAPTURE_INTERVAL - processing_time)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nОстановка пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Сохранение незавершенной сессии
        if is_working and work_session_start and last_detection_time:
            session_duration = int(last_detection_time - work_session_start)
            if db_connection_ok:
                save_work_session_to_db(work_session_start, last_detection_time, session_duration)
            print(f"Завершена незаконченная сессия. Длительность: {session_duration} сек")
        
        # Очистка
        try:
            if os.path.exists(ram_disk_path):
                for filename in os.listdir(ram_disk_path):
                    file_path = os.path.join(ram_disk_path, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Ошибка при очистке RAM диска: {e}")
            
        video_stream.release()
        if SHOW_DETECTION:
            cv2.destroyAllWindows()

def show_status_screen(text, color):
    """Вспомогательная функция для отображения статуса при ошибках/паузе"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, text, (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    cv2.imshow('Chef Detection Debug', frame)
    if (cv2.waitKey(1) & 0xFF) == ord('q'):
        raise KeyboardInterrupt
