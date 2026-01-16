import cv2
import time
import threading
import re
from collections import deque
from config import (
    BUFFER_SIZE, RECONNECT_TIMEOUT, MAX_RECONNECT_ATTEMPTS,
    DECODE_ERROR_THRESHOLD, DECODE_ERROR_WINDOW, RECONNECT_ON_DECODE_ERROR
)

# Создаем класс для перехвата ошибок OpenCV
class DecodeErrorMonitor:
    """
    Мониторинг ошибок декодирования
    """
    def __init__(self):
        self.error_timestamps = []
        self.last_error_time = 0
        self.error_patterns = [
            r'error while decoding MB',
            r'left block unavailable',
            r'Stream timeout triggered',
            r'Connection to .* failed',
            r'Сеть недоступна',
            r'network is unreachable'
        ]
        self.lock = threading.Lock()
    
    def check_for_errors(self, error_message):
        """
        Проверяет сообщение об ошибке на наличие ошибок декодирования
        Возвращает True если найдена ошибка
        """
        if not error_message:
            return False
        
        with self.lock:
            for pattern in self.error_patterns:
                if re.search(pattern, error_message, re.IGNORECASE):
                    current_time = time.time()
                    self.error_timestamps.append(current_time)
                    self.last_error_time = current_time
                    
                    # Удаляем старые ошибки (старше DECODE_ERROR_WINDOW)
                    cutoff_time = current_time - DECODE_ERROR_WINDOW
                    self.error_timestamps = [ts for ts in self.error_timestamps if ts > cutoff_time]
                    
                    # Выводим информацию о найденной ошибке
                    print(f"[{time.strftime('%H:%M:%S')}] Обнаружена ошибка декодирования: {error_message[:100]}")
                    return True
        return False
    
    def should_reconnect(self):
        """
        Проверяет, нужно ли переподключаться на основе ошибок
        """
        if not RECONNECT_ON_DECODE_ERROR:
            return False
        
        with self.lock:
            # Проверяем количество ошибок за последний период
            current_time = time.time()
            cutoff_time = current_time - DECODE_ERROR_WINDOW
            recent_errors = [ts for ts in self.error_timestamps if ts > cutoff_time]
            
            if len(recent_errors) >= DECODE_ERROR_THRESHOLD:
                # Сбрасываем счетчик после принятия решения о переподключении
                self.error_timestamps.clear()
                print(f"[{time.strftime('%H:%M:%S')}] Превышен порог ошибок: {len(recent_errors)}/{DECODE_ERROR_THRESHOLD} за {DECODE_ERROR_WINDOW} сек")
                return True
        
        return False
    
    def get_error_stats(self):
        """Возвращает статистику ошибок"""
        with self.lock:
            current_time = time.time()
            cutoff_time = current_time - DECODE_ERROR_WINDOW
            recent_errors = [ts for ts in self.error_timestamps if ts > cutoff_time]
            
            return {
                'total_errors': len(self.error_timestamps),
                'recent_errors': len(recent_errors),
                'last_error': self.last_error_time,
                'window_size': DECODE_ERROR_WINDOW,
                'threshold': DECODE_ERROR_THRESHOLD
            }


class VideoStream:
    """
    Класс для захвата видео в отдельном потоке с механизмом переподключения
    и мониторингом ошибок декодирования
    """
    def __init__(self, rtsp_url, buffer_size=BUFFER_SIZE, reconnect_timeout=RECONNECT_TIMEOUT, 
                 max_reconnect_attempts=MAX_RECONNECT_ATTEMPTS):
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.reconnect_timeout = reconnect_timeout
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self.reconnect_attempts = 0
        self.decode_error_monitor = DecodeErrorMonitor()
        self.last_reconnect_time = 0
        self.reconnect_cooldown = 30  # Минимальное время между переподключениями (сек)
        
        self.cap = None
        self.initialize_capture()
        
        # Буфер для хранения последнего кадра
        self.frame_buffer = deque(maxlen=self.buffer_size)
        self.lock = threading.Lock()
        self.stopped = False
        self.grabbed = False
        self.current_frame = None
        self.last_valid_frame_time = time.time()
        self.last_status_check = time.time()
        
    def initialize_capture(self):
        """Инициализация захвата видео с обработкой ошибок"""
        try:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                
            print(f"[{time.strftime('%H:%M:%S')}] Подключение к камере: {self.rtsp_url[:50]}...")
            
            # Для OpenCV используем параметры FFMPEG
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            # Устанавливаем параметры для уменьшения проблем
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Пробуем установить таймауты
            try:
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)  # Таймаут открытия
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 30000)  # Таймаут чтения
            except:
                pass  # Некоторые камеры не поддерживают эти параметры
            
            # Проверяем, открылось ли видео
            if not self.cap.isOpened():
                raise Exception(f"Не удалось открыть RTSP поток")
            
            # Пробуем прочитать первый кадр для проверки
            for _ in range(3):  # 3 попытки
                grabbed, _ = self.cap.read()
                if grabbed:
                    break
                time.sleep(0.1)
            
            self.reconnect_attempts = 0
            print(f"[{time.strftime('%H:%M:%S')}] Камера успешно подключена")
            return True
            
        except Exception as e:
            error_msg = f"Ошибка инициализации камеры: {e}"
            print(f"[{time.strftime('%H:%M:%S')}] {error_msg}")
            self.decode_error_monitor.check_for_errors(error_msg)
            return False
    
    def check_decode_errors(self):
        """Проверяет необходимость переподключения из-за ошибок декодирования"""
        # Проверяем статистику ошибок
        if not RECONNECT_ON_DECODE_ERROR:
            return False
        
        if self.decode_error_monitor.should_reconnect():
            current_time = time.time()
            
            # Проверяем, не переподключались ли мы недавно
            if current_time - self.last_reconnect_time > self.reconnect_cooldown:
                return True
        
        return False
    
    def reconnect(self):
        """Переподключение к камере"""
        current_time = time.time()
        self.last_reconnect_time = current_time
        
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"[{time.strftime('%H:%M:%S')}] Достигнут лимит попыток переподключения ({self.max_reconnect_attempts})")
            return False
            
        self.reconnect_attempts += 1
        print(f"[{time.strftime('%H:%M:%S')}] Попытка переподключения {self.reconnect_attempts}/{self.max_reconnect_attempts}...")
        
        success = self.initialize_capture()
        
        if success:
            print(f"[{time.strftime('%H:%M:%S')}] Переподключение успешно")
            self.last_valid_frame_time = time.time()
            return True
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Ошибка переподключения, следующая попытка через {self.reconnect_timeout} сек...")
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
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self.stopped:
            try:
                # Периодическая проверка статуса (раз в 30 секунд)
                current_time = time.time()
                if current_time - self.last_status_check > 30:
                    self.last_status_check = current_time
                    status = self.get_status()
                    if status['decode_errors']['recent_errors'] > 0:
                        print(f"[{time.strftime('%H:%M:%S')}] Статистика ошибок: {status['decode_errors']['recent_errors']} ошибок за последние {DECODE_ERROR_WINDOW} сек")
                
                # Проверяем необходимость переподключения из-за ошибок декодирования
                if self.check_decode_errors():
                    print(f"[{time.strftime('%H:%M:%S')}] Инициирую переподключение из-за ошибок декодирования...")
                    if not self.reconnect():
                        print(f"[{time.strftime('%H:%M:%S')}] Не удалось переподключиться. Останавливаю поток.")
                        break
                    continue
                
                if self.cap is None or not self.cap.isOpened():
                    print(f"[{time.strftime('%H:%M:%S')}] Камера не подключена, пробую переподключиться...")
                    if not self.reconnect():
                        print(f"[{time.strftime('%H:%M:%S')}] Не удалось переподключиться. Останавливаю поток.")
                        break
                    continue
                
                grabbed, frame = self.cap.read()
                
                if grabbed and frame is not None and frame.size > 0:
                    with self.lock:
                        self.grabbed = grabbed
                        self.current_frame = frame
                        self.last_valid_frame_time = time.time()
                        consecutive_errors = 0  # Сбрасываем счетчик последовательных ошибок
                        
                        # Очищаем буфер и добавляем только последний кадр
                        self.frame_buffer.clear()
                        self.frame_buffer.append(frame)
                else:
                    # Проблема с получением кадра
                    consecutive_errors += 1
                    
                    # Периодически выводим информацию о состоянии
                    if consecutive_errors % 10 == 0:
                        print(f"[{time.strftime('%H:%M:%S')}] Не удалось получить кадр. Последовательных ошибок: {consecutive_errors}")
                    
                    # Регистрируем ошибку декодирования
                    error_msg = "Не удалось получить кадр с камеры"
                    self.decode_error_monitor.check_for_errors(error_msg)
                    
                    # Если слишком много ошибок подряд, пробуем переподключиться
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"[{time.strftime('%H:%M:%S')}] Слишком много последовательных ошибок ({consecutive_errors}). Пробую переподключиться...")
                        if not self.reconnect():
                            break
                        consecutive_errors = 0
                        continue
                    
                    # Проверяем таймаут без валидных кадров
                    if time.time() - self.last_valid_frame_time > 5.0:
                        print(f"[{time.strftime('%H:%M:%S')}] Без валидных кадров более 5 секунд. Пробую переподключиться...")
                        if not self.reconnect():
                            break
                        consecutive_errors = 0
                        continue
                
                # Короткая пауза для предотвращения загрузки CPU
                time.sleep(0.001)
                
            except Exception as e:
                # Ловим все исключения и логируем их как ошибки декодирования
                error_msg = str(e)
                print(f"[{time.strftime('%H:%M:%S')}] Исключение в потоке захвата видео: {error_msg}")
                
                # Регистрируем ошибку
                self.decode_error_monitor.check_for_errors(error_msg)
                
                consecutive_errors += 1
                
                # Если слишком много исключений, пробуем переподключиться
                if consecutive_errors >= max_consecutive_errors:
                    if not self.reconnect():
                        break
                    consecutive_errors = 0
                
                time.sleep(1)  # Делаем паузу после исключения
    
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
            self.cap = None
        print(f"[{time.strftime('%H:%M:%S')}] Видеопоток остановлен")
    
    def get_status(self):
        """Возвращает статус видеопотока"""
        with self.lock:
            error_stats = self.decode_error_monitor.get_error_stats()
            return {
                'is_opened': self.cap.isOpened() if self.cap else False,
                'reconnect_attempts': self.reconnect_attempts,
                'last_valid_frame': time.time() - self.last_valid_frame_time,
                'frame_buffer_size': len(self.frame_buffer),
                'decode_errors': error_stats
            }
