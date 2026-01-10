# system.py
import time
import threading
import queue
import os
import posixpath
from datetime import datetime

from config import Config
from database import init_db, save_roll_count
from camera import USBCamera
from detector import YOLODetector
from scale import ScaleReader
from tts import PiperTTS
from voice import VoiceService
from sftp_client import SFTPHandler # [NEW]

config = Config()

class ScaleSystem:
    def __init__(self):
        # Флаг синхронизации: True, когда система говорит/играет звук
        self.speaking_event = threading.Event()
        
        # [NEW] Инициализация SFTP
        self.sftp = SFTPHandler(config)
        if self.sftp.connect():
            # Проверяем и создаем папки при запуске
            self.sftp.ensure_remote_directories([
                config.REMOTE_DIR_USB, 
                config.REMOTE_DIR_YOLO
            ])
        else:
            print("WARNING: SFTP not available at startup")

        self.usb_cam = USBCamera(config)
        self.yolo_detector = YOLODetector(config)
        self.scale_reader = ScaleReader(config)
        
        self.tts = PiperTTS(config, self.speaking_event)
        self.voice_service = VoiceService(config, self.speaking_event, self.tts)
        
        self.db_available = init_db()
        
        self.capture_queue = queue.Queue()
        self.detection_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        self.running = True
        self.last_capture_time = 0
        
        self.in_session = False
        self.session_max_weight = 0
        self.session_max_detection = 0
        self.pending_max_weight = 0
        self.pending_max_detection = 0
        
        self.last_spoken_weight = 0
        self.change_sound_played = False

        self.last_printed_weight = 0
        self.first_print_done = False
        
        if not self.scale_reader.connect():
            print("Ошибка подключения к весам")
        
        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.detection_thread = threading.Thread(target=self._detection_worker, daemon=True)
        self.result_thread = threading.Thread(target=self._result_worker, daemon=True)
        self.scale_thread = threading.Thread(target=self._scale_worker, daemon=True)
        
        self.capture_thread.start()
        self.detection_thread.start()
        self.result_thread.start()
        self.scale_thread.start()

    def _scale_worker(self):
        while self.running:
            try:
                weight_data = self.scale_reader.read_weight()
                
                if weight_data:
                    current_grams = weight_data['weight_grams']
                    current_kg = weight_data['weight_kg']
                    status = weight_data['status']
                    
                    if status == 'S':
                        diff_print = abs(current_grams - self.last_printed_weight)
                        if not self.first_print_done or diff_print >= config.WEIGHT_TTS_THRESHOLD:
                            print(self.scale_reader.format_output(weight_data))
                            self.last_printed_weight = current_grams
                            self.first_print_done = True

                    threshold = config.WEIGHT_TTS_THRESHOLD
                    diff = current_grams - self.last_spoken_weight
                    abs_diff = abs(diff)

                    if abs_diff < threshold:
                        self.change_sound_played = False

                    if abs_diff >= threshold and not self.change_sound_played:
                        is_increase = diff > 0
                        self.tts.play_change_notification(is_increase)
                        self.change_sound_played = True

                    if status == 'S':
                        if abs_diff >= threshold:
                            self.tts.say_weight(current_kg)
                            self.last_spoken_weight = current_grams
                            self.change_sound_played = False
                    
                    if status == 'S' and current_grams == 0 and self.in_session:
                        if self.pending_max_weight > 0 or self.pending_max_detection > 0:
                            current_time = datetime.now().replace(microsecond=0)
                            if self.db_available:
                                save_roll_count(
                                    point_id=config.POINT_ID,
                                    timestamp=current_time,
                                    hour=current_time.hour,
                                    weight_count=0,
                                    detection_count=0,
                                    max_weight=self.pending_max_weight,
                                    max_detection=self.pending_max_detection,
                                    mass=0.0
                                )
                        
                        self.in_session = False
                        self.session_max_weight = 0
                        self.session_max_detection = 0
                        self.pending_max_weight = 0
                        self.pending_max_detection = 0
                    
                    if status == 'S' and weight_data['is_threshold_exceeded']:
                        if not self.in_session:
                            self.in_session = True
                            self.session_max_weight = 0
                            self.session_max_detection = 0
                            self.pending_max_weight = 0
                            self.pending_max_detection = 0
                        
                        self.request_capture(current_grams, current_kg)
                        self.scale_reader.update_stable_weight(current_grams)
                
                time.sleep(0.1)
            except Exception as e:
                print(f"Ошибка в цикле весов: {e}")
                time.sleep(1)

    def _capture_worker(self):
        while self.running:
            try:
                weight_grams, weight_kg, timestamp_str = self.capture_queue.get(timeout=1.0)
                
                current_time = time.time()
                if current_time - self.last_capture_time < config.COOLDOWN_TIME:
                    wait_time = config.COOLDOWN_TIME - (current_time - self.last_capture_time)
                    time.sleep(wait_time)
                
                if config.FOCUS_DELAY > 0:
                    time.sleep(config.FOCUS_DELAY)
                
                # Формируем путь. Благодаря config.PHOTO_DIRS это будет путь в RAM (/dev/shm/...)
                filename_base = f"{str(config.POINT_ID)}_USB_{timestamp_str}.jpeg"
                local_usb_path = os.path.join(config.PHOTO_DIRS['usb'], filename_base)
                
                if self.usb_cam.capture(local_usb_path):
                    # Загрузка на SFTP
                    remote_usb_path = posixpath.join(config.REMOTE_DIR_USB, filename_base)
                    self.sftp.upload_file(local_usb_path, remote_usb_path)
                    
                    # Передаем путь к файлу в ОЗУ для обработки нейросетью
                    self.detection_queue.put((local_usb_path, weight_grams, weight_kg, timestamp_str))
                else:
                    self.tts.play_camera_notification()
                    self.usb_cam.reconnect()
                
                self.last_capture_time = time.time()
                self.capture_queue.task_done()
            except queue.Empty:
                continue

    def _detection_worker(self):
        while self.running:
            try:
                local_usb_path, weight_grams, weight_kg, timestamp_str = self.detection_queue.get(timeout=1.0)
                
                filename_base_yolo = f"{str(config.POINT_ID)}_YOLO_{timestamp_str}.jpeg"
                # Путь сохранения результата тоже в RAM
                local_yolo_path = os.path.join(config.PHOTO_DIRS['yolo'], filename_base_yolo)
                
                # YOLO читает из ОЗУ и пишет в ОЗУ
                detected_count = self.yolo_detector.detect_and_save(local_usb_path, local_yolo_path)
                
                # Загружаем результат на SFTP
                remote_yolo_path = posixpath.join(config.REMOTE_DIR_YOLO, filename_base_yolo)
                self.sftp.upload_file(local_yolo_path, remote_yolo_path)
                
                # ВАЖНО: Удаляем файлы из RAM-диска после отправки, чтобы не забить память
                try:
                    if os.path.exists(local_usb_path):
                        os.remove(local_usb_path)
                    if os.path.exists(local_yolo_path):
                        os.remove(local_yolo_path)
                except Exception as e:
                    print(f"Error deleting temp files from RAM: {e}")

                self.result_queue.put((weight_grams, weight_kg, detected_count, timestamp_str, remote_yolo_path))
                self.detection_queue.task_done()
            except queue.Empty:
                continue

    def _result_worker(self):
        while self.running:
            try:
                weight_grams, weight_kg, detected_count, timestamp_str, yolo_filename = self.result_queue.get(timeout=1.0)
                weight_count = round(weight_grams / config.WEIGHT_THRESHOLD)
                
                self.session_max_weight = max(self.session_max_weight, weight_count)
                self.session_max_detection = max(self.session_max_detection, detected_count)
                self.pending_max_weight = max(self.pending_max_weight, weight_count)
                self.pending_max_detection = max(self.pending_max_detection, detected_count)
                
                if weight_count > 0 or detected_count > 0:
                    current_time = datetime.now().replace(microsecond=0)
                    if self.db_available:
                        save_roll_count(
                            point_id=config.POINT_ID,
                            timestamp=current_time,
                            hour=current_time.hour,
                            weight_count=weight_count,
                            detection_count=detected_count,
                            max_weight=0,
                            max_detection=0,
                            mass=weight_kg
                        )
                self.result_queue.task_done()
            except queue.Empty:
                continue

    def request_capture(self, weight_grams, weight_kg):
        current_time = datetime.now()
        timestamp_str = current_time.strftime("%Y-%m-%d_%H:%M:%S")
        self.capture_queue.put((weight_grams, weight_kg, timestamp_str))
        return True

    def stop(self):
        self.running = False
        self.tts.stop()
        self.voice_service.stop()
        self.capture_queue.join()
        self.detection_queue.join()
        self.result_queue.join()
        self.scale_reader.close()
        if self.sftp:
            self.sftp.close()
