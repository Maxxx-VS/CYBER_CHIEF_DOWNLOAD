import cv2
import time
import threading
from collections import deque
from config import BUFFER_SIZE, RECONNECT_TIMEOUT, MAX_RECONNECT_ATTEMPTS

class VideoStream:
    """
    Класс для захвата видео в отдельном потоке с механизмом переподключения
    """
    def __init__(self, rtsp_url, buffer_size=BUFFER_SIZE, reconnect_timeout=RECONNECT_TIMEOUT, max_reconnect_attempts=MAX_RECONNECT_ATTEMPTS):
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.reconnect_timeout = reconnect_timeout
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self.reconnect_attempts = 0
        self.cap = None
        self.initialize_capture()
        
        # Буфер для хранения последнего кадра
        self.frame_buffer = deque(maxlen=self.buffer_size)
        self.lock = threading.Lock()
        self.stopped = False
        self.grabbed = False
        self.current_frame = None
        self.last_valid_frame_time = time.time()
        
    def initialize_capture(self):
        """Инициализация захвата видео с обработкой ошибок"""
        try:
            if self.cap is not None:
                self.cap.release()
                
            self.cap = cv2.VideoCapture(self.rtsp_url)
            if not self.cap.isOpened():
                raise Exception(f"Ошибка: Не удалось открыть RTSP поток {self.rtsp_url}")
                
            # Установка параметров для уменьшения задержки
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.reconnect_attempts = 0
            return True
            
        except Exception as e:
            print(f"Ошибка инициализации камеры: {e}")
            return False
            
    def reconnect(self):
        """Переподключение к камере"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"Достигнут лимит попыток переподключения ({self.max_reconnect_attempts})")
            return False
            
        self.reconnect_attempts += 1
        print(f"Попытка переподключения #{self.reconnect_attempts}...")
        
        success = self.initialize_capture()
        
        if success:
            self.last_valid_frame_time = time.time()
            return True
        else:
            time.sleep(self.reconnect_timeout)
            return self.reconnect()
        
    def start(self):
        """Запуск потока захвата видео"""
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        return self
        
    def update(self):
        """Основной цикл захвата кадров"""
        while not self.stopped:
            try:
                if self.cap is None or not self.cap.isOpened():
                    if not self.reconnect():
                        break
                    continue
                    
                grabbed, frame = self.cap.read()
                if grabbed and frame is not None and frame.size > 0:
                    with self.lock:
                        self.grabbed = grabbed
                        self.current_frame = frame
                        self.last_valid_frame_time = time.time()
                        # Очищаем буфер и добавляем только последний кадр
                        self.frame_buffer.clear()
                        self.frame_buffer.append(frame)
                else:
                    # Проблема с получением кадра
                    if time.time() - self.last_valid_frame_time > 5.0:  # 5 секунд без валидных кадров
                        if not self.reconnect():
                            break
                            
            except Exception as e:
                print(f"Ошибка в потоке захвата видео: {e}")
                if not self.reconnect():
                    break
                    
            time.sleep(0.001)
                    
    def read(self):
        """Чтение последнего кадра"""
        with self.lock:
            if self.frame_buffer:
                return True, self.frame_buffer[-1].copy()
            return False, None
            
    def stop(self):
        """Остановка потока"""
        self.stopped = True
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
            
    def release(self):
        """Освобождение ресурсов"""
        self.stop()
        if self.cap is not None:
            self.cap.release()
