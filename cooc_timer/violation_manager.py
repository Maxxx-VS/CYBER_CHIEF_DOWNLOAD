# violation_manager.py
from config import COUNT_VIOLATIONS, SOUND_PATH_WARNING
import os
import subprocess
import threading
import time
from sftp_client import SFTPUploader
import cv2
from datetime import datetime
from config import ID_POINT, RAM_DISK_PATH

class ViolationManager:
    def __init__(self):
        self.consecutive_violations = 0
        self.last_violation_time = 0
        self.last_violation_frame = None
        self.last_violation_data = None
        self.speaking_event = threading.Event()
        self.uploader = SFTPUploader()
        
    def record_violation(self, frame, violation_info):
        """
        Записывает нарушение в буфер. Сохраняет фото только при достижении COUNT_VIOLATIONS
        """
        self.consecutive_violations += 1
        self.last_violation_time = time.time()
        self.last_violation_frame = frame.copy()
        self.last_violation_data = violation_info
        
        # Если достигли порога - сохраняем фото и воспроизводим звук
        if self.consecutive_violations >= COUNT_VIOLATIONS:
            self._save_and_notify()
    
    def reset_violations(self):
        """Сбрасывает счетчик нарушений"""
        self.consecutive_violations = 0
        self.last_violation_frame = None
        self.last_violation_data = None
    
    def check_timeout(self, timeout=5):
        """
        Проверяет таймаут между нарушениями.
        Если прошло больше timeout секунд - сбрасываем счетчик.
        """
        if self.consecutive_violations > 0 and (time.time() - self.last_violation_time) > timeout:
            self.reset_violations()
            return True
        return False
    
    def _save_and_notify(self):
        """Сохраняет последнее фото нарушения и воспроизводит звуковое предупреждение"""
        if self.last_violation_frame is None or self.last_violation_data is None:
            return
        
        # Сохраняем фото
        self._save_violation_image()
        
        # Воспроизводим звуковое предупреждение
        self._play_warning_sound()
        
        # Сбрасываем счетчик
        self.consecutive_violations = 0
    
    def _save_violation_image(self):
        """Сохраняет изображение нарушения на SFTP"""
        # Подготавливаем кадр для сохранения
        violation_frame = self.last_violation_frame.copy()
        timestamp = self.last_violation_data['timestamp']
        
        # Рисуем bbox человека
        person_bbox = self.last_violation_data['person_bbox']
        x1, y1, x2, y2 = person_bbox
        cv2.rectangle(violation_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
        
        # Добавляем текст с нарушением
        cv2.putText(violation_frame, f'VIOLATION: No gloves ({self.consecutive_violations} times)', 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(violation_frame, f'Timestamp: {datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")}', 
                   (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Формируем имя файла
        dt_object = datetime.fromtimestamp(timestamp)
        date_str = dt_object.strftime("%Y-%m-%d")
        time_str = dt_object.strftime("%H:%M:%S")
        
        filename_base = f"{ID_POINT}_VIOLATION_{date_str}_{time_str}"
        filename = f"{filename_base}.jpeg"
        
        # Сохраняем временно в RAM диск
        local_path = os.path.join(RAM_DISK_PATH, filename)
        cv2.imwrite(local_path, violation_frame)
        
        # Загружаем на SFTP и удаляем локальный файл
        self.uploader.upload_file(local_path, filename)
    
    def _play_warning_sound(self):
        """Воспроизводит звуковое предупреждение в отдельном потоке"""
        if not SOUND_PATH_WARNING or not os.path.exists(SOUND_PATH_WARNING):
            print(f"Предупреждение: Файл звука не найден: {SOUND_PATH_WARNING}")
            return
        
        # Запускаем в отдельном потоке, чтобы не блокировать основной поток
        threading.Thread(
            target=self._play_sound_worker,
            args=(SOUND_PATH_WARNING,),
            daemon=True
        ).start()
    
    def _play_sound_worker(self, sound_path):
        """Воркер для воспроизведения звука"""
        # Ждем, если уже воспроизводится другой звук
        timeout = 5.0
        start_wait = time.time()
        
        while self.speaking_event.is_set():
            if time.time() - start_wait > timeout:
                break
            time.sleep(0.1)
        
        # Даем время на освобождение звуковой карты
        time.sleep(0.2)
        
        # Воспроизводим звук
        self.speaking_event.set()
        try:
            # Используем mpg123 для воспроизведения MP3
            cmd = ['mpg123', '-o', 'alsa', '-q', '-f', '32768', sound_path]
            subprocess.run(cmd, capture_output=True)
        except Exception as e:
            print(f"Ошибка воспроизведения звука: {e}")
        finally:
            self.speaking_event.clear()
    
    def get_consecutive_count(self):
        """Возвращает текущее количество подряд идущих нарушений"""
        return self.consecutive_violations

# Глобальный экземпляр менеджера нарушений
violation_manager = ViolationManager()
