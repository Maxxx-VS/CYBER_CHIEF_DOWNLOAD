import cv2
import time
import threading
from collections import deque
from config import RTSP_URL, BUFFER_SIZE, RECONNECT_TIMEOUT, MAX_RECONNECT_ATTEMPTS, DECODE_ERROR_THRESHOLD, DECODE_ERROR_WINDOW, RECONNECT_ON_DECODE_ERROR

class VideoStream:
    """
    Класс для захвата видео в отдельном потоке с механизмом переподключения
    и отслеживания ошибок декодирования
    """
    def __init__(self, rtsp_url=RTSP_URL, buffer_size=BUFFER_SIZE, 
                 reconnect_timeout=RECONNECT_TIMEOUT, max_reconnect_attempts=MAX_RECONNECT_ATTEMPTS):
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.reconnect_timeout = reconnect_timeout
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # Параметры для отслеживания ошибок декодирования
        self.decode_error_threshold = DECODE_ERROR_THRESHOLD
        self.decode_error_window = DECODE_ERROR_WINDOW
        self.reconnect_on_decode_error = RECONNECT_ON_DECODE_ERROR
        
        # Счетчики ошибок декодирования
        self.decode_error_times = deque(maxlen=self.decode_error_threshold * 2)
        
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
        
        # Счетчик последовательных неудачных чтений
        self.consecutive_read_errors = 0
        self.max_consecutive_errors = 10  # Максимум 10 ошибок подряд
        
    def initialize_capture(self):
        """Инициализация захвата видео с обработкой ошибок"""
        try:
            if self.cap is not None:
                self.cap.release()
                
            print(f"Подключение к RTSP: {self.rtsp_url}")
            self.cap = cv2.VideoCapture(self.rtsp_url)
            
            # Настройка параметров для улучшения стабильности
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
            self.cap.set(cv2.CAP_PROP_FPS, 10)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
            
            if not self.cap.isOpened():
                raise Exception(f"Ошибка: Не удалось открыть RTSP поток {self.rtsp_url}")
                
            self.reconnect_attempts = 0
            self.consecutive_read_errors = 0
            print("Подключение к камере успешно")
            return True
            
        except Exception as e:
            print(f"Ошибка инициализации камеры: {e}")
            return False
    
    def record_decode_error(self):
        """Записывает ошибку декодирования и проверяет, нужно ли переподключаться"""
        if not self.reconnect_on_decode_error:
            return False
            
        current_time = time.time()
        self.decode_error_times.append(current_time)
        
        # Удаляем старые ошибки (старше окна отслеживания)
        while (self.decode_error_times and 
               current_time - self.decode_error_times[0] > self.decode_error_window):
            self.decode_error_times.popleft()
        
        # Проверяем, превышен ли порог ошибок
        if len(self.decode_error_times) >= self.decode_error_threshold:
            print(f"Превышен порог ошибок декодирования: {len(self.decode_error_times)} ошибок за {self.decode_error_window} секунд")
            return True
        
        return False
    
    def reconnect(self):
        """Переподключение к камере с учетом ошибок декодирования"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"Достигнут лимит попыток переподключения ({self.max_reconnect_attempts})")
            return False
            
        self.reconnect_attempts += 1
        print(f"Попытка переподключения #{self.reconnect_attempts}...")
        
        # Сброс счетчиков ошибок декодирования при переподключении
        self.decode_error_times.clear()
        self.consecutive_read_errors = 0
        
        success = self.initialize_capture()
        
        if success:
            self.last_valid_frame_time = time.time()
            print("Переподключение успешно")
            return True
        else:
            print(f"Ошибка переподключения, следующая попытка через {self.reconnect_timeout} секунд")
            time.sleep(self.reconnect_timeout)
            return self.reconnect()
    
    def check_decode_errors_and_reconnect(self):
        """Проверяет ошибки декодирования и инициирует переподключение при необходимости"""
        if self.record_decode_error():
            print("Обнаружены множественные ошибки декодирования. Инициирую переподключение...")
            return self.reconnect()
        return True
    
    def detect_decode_errors(self):
        """
        Детектирование ошибок декодирования на основе качества кадра.
        В реальной системе можно расширить для анализа конкретных ошибок.
        """
        # Упрощенная проверка: если много последовательных ошибок чтения,
        # считаем это проблемой декодирования
        if self.consecutive_read_errors > 5:
            print(f"Обнаружено {self.consecutive_read_errors} последовательных ошибок чтения")
            self.record_decode_error()
            
        # Проверяем, нужно ли переподключаться из-за ошибок
        if not self.check_decode_errors_and_reconnect():
            return False
        return True
        
    def start(self):
        """Запуск потока захвата видео"""
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        return self
    
    def update(self):
        """Основной цикл захвата кадров с отслеживанием ошибок декодирования"""
        while not self.stopped:
            try:
                if self.cap is None or not self.cap.isOpened():
                    if not self.reconnect():
                        break
                    continue
                
                # Проверяем ошибки декодирования
                if not self.detect_decode_errors():
                    continue
                
                grabbed, frame = self.cap.read()
                if grabbed and frame is not None and frame.size > 0:
                    with self.lock:
                        self.grabbed = grabbed
                        self.current_frame = frame
                        self.last_valid_frame_time = time.time()
                        self.consecutive_read_errors = 0  # Сбрасываем счетчик ошибок
                        self.frame_buffer.clear()
                        self.frame_buffer.append(frame)
                else:
                    # Увеличиваем счетчик ошибок чтения
                    self.consecutive_read_errors += 1
                    
                    # Проверяем, не пора ли переподключаться из-за отсутствия кадров
                    if time.time() - self.last_valid_frame_time > 5.0:
                        print(f"Нет валидных кадров более 5 секунд. Ошибок чтения: {self.consecutive_read_errors}")
                        if not self.reconnect():
                            break
                        
            except cv2.error as e:
                self.consecutive_read_errors += 1
                error_msg = str(e)
                
                # Фиксируем ошибки декодирования
                if any(keyword in error_msg for keyword in ['decoding', 'h264', 'MB', 'block unavailable']):
                    print(f"Ошибка декодирования: {error_msg}")
                    self.record_decode_error()
                
                if self.consecutive_read_errors > self.max_consecutive_errors:
                    print(f"Превышено максимальное количество ошибок ({self.max_consecutive_errors})")
                    if not self.reconnect():
                        break
                        
            except Exception as e:
                print(f"Ошибка в потоке захвата видео: {e}")
                if not self.reconnect():
                    break
                    
            time.sleep(0.01)  # Небольшая пауза для снижения нагрузки
    
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
            
    def manual_reconnect(self):
        """Ручное инициирование переподключения"""
        print("Ручной запрос на переподключение...")
        return self.reconnect()
