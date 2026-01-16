import cv2
import time
import threading
from collections import deque
from config import (
    RTSP_URL, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, 
    BUFFER_SIZE, RECONNECT_TIMEOUT, MAX_RECONNECT_ATTEMPTS, 
    HEALTH_CHECK_INTERVAL, DECODE_ERROR_THRESHOLD, 
    DECODE_ERROR_WINDOW, RECONNECT_ON_DECODE_ERROR
)

class VideoStream:
    """
    Класс для захвата видео в отдельном потоке с механизмом переподключения
    и обработкой ошибок декодирования
    """
    def __init__(self, rtsp_url=None, width=None, height=None, fps=None, 
                 buffer_size=None, reconnect_timeout=None, 
                 max_reconnect_attempts=None, health_check_interval=None):
        
        # Получаем настройки из переменных окружения или используем значения по умолчанию
        self.rtsp_url = rtsp_url or RTSP_URL
        self.width = width or CAMERA_WIDTH
        self.height = height or CAMERA_HEIGHT
        self.fps = fps or CAMERA_FPS
        self.buffer_size = buffer_size or BUFFER_SIZE
        self.reconnect_timeout = reconnect_timeout or RECONNECT_TIMEOUT
        self.max_reconnect_attempts = max_reconnect_attempts or MAX_RECONNECT_ATTEMPTS
        self.health_check_interval = health_check_interval or HEALTH_CHECK_INTERVAL
        
        # Настройки обработки ошибок декодирования
        self.decode_error_threshold = DECODE_ERROR_THRESHOLD
        self.decode_error_window = DECODE_ERROR_WINDOW
        self.reconnect_on_decode_error = RECONNECT_ON_DECODE_ERROR
        
        # Счетчики ошибок декодирования
        self.decode_errors = deque(maxlen=100)  # Храним временные метки ошибок
        self.last_decode_error_check = time.time()
        self.decode_error_lock = threading.Lock()
        
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
        self.consecutive_empty_frames = 0
        self.max_consecutive_empty_frames = 15  # Максимальное количество пустых кадров подряд
        
    def initialize_capture(self):
        """Инициализация захвата видео с обработкой ошибок"""
        try:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                
            print(f"Подключение к камере: {self.rtsp_url}")
            
            # Настройка параметров для FFmpeg для лучшей обработки RTSP
            ffmpeg_options = {
                'rtsp_transport': 'tcp',  # Используем TCP для стабильности
                'buffer_size': '655360',  # Увеличиваем размер буфера
                'max_delay': '500000',    # Максимальная задержка
                'flags': 'low_delay',     # Флаг низкой задержки
                'stimeout': '3000000',    # Таймаут подключения (3 сек в микросекундах)
                'analyzeduration': '1000000',  # Время анализа потока
                'probesize': '500000'     # Размер анализа потока
            }
            
            # Формируем строку параметров для OpenCV
            option_str = ''
            for key, value in ffmpeg_options.items():
                option_str += f'{key}={value}:'
            option_str = option_str.rstrip(':')
            
            # Формируем полный URL с параметрами
            full_url = self.rtsp_url
            if '?' not in full_url:
                full_url += f'?{option_str}'
            else:
                full_url += f'&{option_str}'
            
            self.cap = cv2.VideoCapture(full_url, cv2.CAP_FFMPEG)
            
            # Альтернативный вариант без параметров в URL
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.rtsp_url)
                for key, value in ffmpeg_options.items():
                    self.cap.set(getattr(cv2, f'CAP_PROP_{key.upper()}', -1), value)
            
            if not self.cap.isOpened():
                raise Exception(f"Ошибка: Не удалось открыть IP камеру {self.rtsp_url}")
                
            # Установка параметров камеры
            if self.width > 0:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height > 0:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if self.fps > 0:
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Сбрасываем счетчики ошибок при успешном подключении
            with self.decode_error_lock:
                self.decode_errors.clear()
            self.reconnect_attempts = 0
            self.consecutive_empty_frames = 0
            
            print(f"Камера успешно подключена: {self.rtsp_url}")
            return True
            
        except Exception as e:
            print(f"Ошибка инициализации камеры: {e}")
            return False
    
    def record_decode_error(self, error_type="unknown"):
        """Записываем факт ошибки декодирования"""
        current_time = time.time()
        with self.decode_error_lock:
            self.decode_errors.append((current_time, error_type))
            
            # Очищаем старые ошибки (старше окна мониторинга)
            while self.decode_errors and current_time - self.decode_errors[0][0] > self.decode_error_window:
                self.decode_errors.popleft()
            
            # Логируем при большом количестве ошибок
            error_count = len(self.decode_errors)
            if error_count > self.decode_error_threshold * 0.7:  # 70% от порога
                print(f"Предупреждение: накоплено {error_count} ошибок декодирования за последние {self.decode_error_window} сек")
    
    def should_reconnect_due_to_decode_errors(self):
        """Проверяем, нужно ли переподключаться из-за ошибок декодирования"""
        if not self.reconnect_on_decode_error:
            return False
        
        current_time = time.time()
        
        # Проверяем не чаще чем раз в 5 секунд
        if current_time - self.last_decode_error_check < 5:
            return False
        
        self.last_decode_error_check = current_time
        
        with self.decode_error_lock:
            # Очищаем старые ошибки
            while self.decode_errors and current_time - self.decode_errors[0][0] > self.decode_error_window:
                self.decode_errors.popleft()
            
            error_count = len(self.decode_errors)
            
            if error_count >= self.decode_error_threshold:
                print(f"Порог ошибок декодирования превышен: {error_count}/{self.decode_error_threshold} за {self.decode_error_window} сек. Инициирую переподключение.")
                return True
        
        return False
    
    def reconnect(self):
        """Переподключение к камере"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"Достигнут лимит попыток переподключения ({self.max_reconnect_attempts}). Ожидание...")
            # Сбрасываем счетчик после паузы
            time.sleep(60)
            self.reconnect_attempts = 0
            return self.reconnect()
        
        self.reconnect_attempts += 1
        print(f"Попытка переподключения {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        # Освобождаем старый захват
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        time.sleep(self.reconnect_timeout)
        success = self.initialize_capture()
        
        if success:
            self.last_valid_frame_time = time.time()
            return True
        else:
            # Если не удалось, ждем и пробуем снова
            wait_time = min(self.reconnect_timeout * 2, 30)  # Увеличиваем время ожидания, но не более 30 сек
            print(f"Переподключение не удалось. Следующая попытка через {wait_time} сек.")
            time.sleep(wait_time)
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
                # Проверяем, нужно ли переподключиться из-за ошибок декодирования
                if self.should_reconnect_due_to_decode_errors():
                    if not self.reconnect():
                        break
                    # После переподключения очищаем ошибки
                    with self.decode_error_lock:
                        self.decode_errors.clear()
                    continue
                
                if self.cap is None or not self.cap.isOpened():
                    if not self.reconnect():
                        break
                    continue
                
                grabbed, frame = self.cap.read()
                
                # Проверяем на ошибки декодирования (пустой или поврежденный кадр)
                if not grabbed:
                    self.consecutive_empty_frames += 1
                    self.record_decode_error("grab_failed")
                    
                    if self.consecutive_empty_frames >= self.max_consecutive_empty_frames:
                        print(f"Получено {self.consecutive_empty_frames} пустых кадров подряд. Возможна ошибка декодирования.")
                        if not self.reconnect():
                            break
                        continue
                    
                    time.sleep(0.01)  # Короткая пауза при ошибке захвата
                    continue
                
                if frame is None:
                    self.consecutive_empty_frames += 1
                    self.record_decode_error("null_frame")
                    
                    if self.consecutive_empty_frames >= self.max_consecutive_empty_frames:
                        print(f"Получено {self.consecutive_empty_frames} пустых кадров подряд. Возможна ошибка декодирования.")
                        if not self.reconnect():
                            break
                        continue
                    
                    time.sleep(0.01)
                    continue
                
                if frame.size == 0:
                    self.consecutive_empty_frames += 1
                    self.record_decode_error("empty_frame")
                    
                    if self.consecutive_empty_frames >= self.max_consecutive_empty_frames:
                        print(f"Получено {self.consecutive_empty_frames} пустых кадров подряд. Возможна ошибка декодирования.")
                        if not self.reconnect():
                            break
                        continue
                    
                    time.sleep(0.01)
                    continue
                
                # Валидный кадр получен
                self.consecutive_empty_frames = 0
                
                with self.lock:
                    self.grabbed = grabbed
                    self.current_frame = frame
                    self.last_valid_frame_time = time.time()
                    # Очищаем буфер и добавляем только последний кадр
                    if self.frame_buffer:
                        self.frame_buffer.clear()
                    self.frame_buffer.append(frame)
                
            except cv2.error as e:
                print(f"OpenCV ошибка в потоке захвата видео: {e}")
                self.record_decode_error(f"cv2_error: {str(e)[:50]}")
                
                if not self.reconnect():
                    break
                
            except Exception as e:
                print(f"Исключение в потоке захвата видео: {e}")
                self.record_decode_error(f"exception: {str(e)[:50]}")
                
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
                    print(f"Долгое время нет валидных кадров: {time_since_last_frame:.1f} сек. Пытаюсь переподключиться.")
                    with self.lock:
                        self.grabbed = False
                        self.current_frame = None
                        if self.frame_buffer:
                            self.frame_buffer.clear()
                    
                    if not self.reconnect():
                        break
                
            except Exception as e:
                print(f"Ошибка в health_check: {e}")
            
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
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if hasattr(self, 'health_thread') and self.health_thread.is_alive():
            self.health_thread.join(timeout=2.0)
    
    def release(self):
        """Освобождение ресурсов"""
        self.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
