import cv2
import time
import threading
from collections import deque
from config import RTSP_URL, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, BUFFER_SIZE, RECONNECT_TIMEOUT, MAX_RECONNECT_ATTEMPTS, HEALTH_CHECK_INTERVAL

class VideoStream:
    """
    Класс для захвата видео в отдельном потоке с механизмом переподключения
    """
    def __init__(self, rtsp_url=None, width=None, height=None, fps=None, buffer_size=None, 
                 reconnect_timeout=None, max_reconnect_attempts=None, health_check_interval=None):
        
        # Получаем настройки из переменных окружения или используем значения по умолчанию
        self.rtsp_url = rtsp_url or RTSP_URL
        self.width = width or CAMERA_WIDTH
        self.height = height or CAMERA_HEIGHT
        self.fps = fps or CAMERA_FPS
        self.buffer_size = buffer_size or BUFFER_SIZE
        self.reconnect_timeout = reconnect_timeout or RECONNECT_TIMEOUT
        self.max_reconnect_attempts = max_reconnect_attempts or MAX_RECONNECT_ATTEMPTS
        self.health_check_interval = health_check_interval or HEALTH_CHECK_INTERVAL
        
        self.reconnect_attempts = 0
        
        # Инициализация захвата видео
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
                raise Exception(f"Ошибка: Не удалось открыть IP камеру {self.rtsp_url}")
                
            # Установка параметров камеры
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            self.reconnect_attempts = 0
            return True
            
        except Exception as e:
            return False
            
    def reconnect(self):
        """Переподключение к камере"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            return False
            
        self.reconnect_attempts += 1
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
        
        # Запуск потока проверки здоровья
        self.health_thread = threading.Thread(target=self.health_check, args=())
        self.health_thread.daemon = True
        self.health_thread.start()
        
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
                    if time.time() - self.last_valid_frame_time > self.health_check_interval * 2:
                        if not self.reconnect():
                            break
                            
            except Exception as e:
                if not self.reconnect():
                    break
                    
            time.sleep(0.001)  # Минимальная задержка для реального времени
                    
    def health_check(self):
        """Поток для проверки здоровья видеопотока"""
        while not self.stopped:
            try:
                current_time = time.time()
                time_since_last_frame = current_time - self.last_valid_frame_time
                
                # Если долго не было валидных кадров, пытаемся переподключиться
                if time_since_last_frame > self.health_check_interval * 3:
                    with self.lock:
                        self.grabbed = False
                        self.current_frame = None
                        self.frame_buffer.clear()
                    
                    if not self.reconnect():
                        break
                        
            except Exception as e:
                pass
                
            time.sleep(self.health_check_interval)
            
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
        if hasattr(self, 'health_thread'):
            self.health_thread.join(timeout=2.0)
            
    def release(self):
        """Освобождение ресурсов"""
        self.stop()
        if self.cap is not None:
            self.cap.release()