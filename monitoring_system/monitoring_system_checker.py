import os
import glob
import cv2
import socket
import subprocess
import time
import serial
import threading
import queue
import re
import warnings
from pathlib import Path
from dotenv import load_dotenv

class CameraChecker:
    def __init__(self):
        self.scale_cache_time = 0
        self.scale_cache_duration = 10
        self.scale_cache_status = None
        
        # Кэш для USB-камеры
        self.usb_cache_time = 0
        self.usb_cache_duration = 5  # кэшируем на 5 секунд
        self.usb_cache_status = None
        
        # Определяем путь к .env файлу и загружаем его один раз при старте
        current_dir = Path(__file__).parent
        self.env_path = current_dir.parent / "enviroment" / ".env"
        load_dotenv(dotenv_path=self.env_path)
        
        # Кэшируем параметры камер сразу
        self.cameras_config = {
            'COOK': os.getenv('RTSP_URL_COOK'),
            'CASSIR': os.getenv('RTSP_URL_CASSIR'),
            'CLIENT': os.getenv('RTSP_URL_CLIENT')
        }
        
        warnings.filterwarnings('ignore', category=UserWarning)
    
    def get_ip_cameras(self):
        """Получение списка IP камер из закэшированных настроек"""
        ip_cameras = []
        for cam_name, rtsp_url in self.cameras_config.items():
            if rtsp_url:
                try:
                    if '@' in rtsp_url:
                        ip_part = rtsp_url.split('@')[1].split('/')[0]
                    else:
                        ip_part = rtsp_url.split('//')[1].split('/')[0]
                    
                    ip = ip_part.split(':')[0] if ':' in ip_part else ip_part
                    port = int(ip_part.split(':')[1]) if ':' in ip_part else 554
                        
                    ip_cameras.append({
                        'name': cam_name, 'url': rtsp_url, 'ip': ip, 'port': port
                    })
                except Exception:
                    continue
        return ip_cameras

    def check_ip_camera_ping(self, ip):
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '2', ip], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception: 
            return False

    def check_ip_camera_port(self, ip, port=554):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                return sock.connect_ex((ip, port)) == 0
        except Exception: 
            return False

    def check_ip_camera_rtsp(self, camera_info):
        # OpenCV check
        try:
            cap = cv2.VideoCapture(camera_info['url'])
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None: 
                    return True
        except Exception: 
            pass
        
        # FFprobe check
        try:
            result = subprocess.run(['ffprobe', '-v', 'quiet', '-timeout', '5000000', '-i', camera_info['url']], 
                                    capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception: 
            return False

    def check_ip_camera(self, camera_info):
        if self.check_ip_camera_ping(camera_info['ip']) or self.check_ip_camera_port(camera_info['ip'], camera_info['port']):
            return self.check_ip_camera_rtsp(camera_info)
        return False

    def check_usb_camera(self):
        """Проверка конкретной USB-камеры по ID 5843:7884 с кэшированием"""
        current_time = time.time()
        
        # Проверяем кэш
        if self.usb_cache_status is not None and current_time - self.usb_cache_time < self.usb_cache_duration:
            return self.usb_cache_status
        
        # Проверяем только конкретную камеру по ID
        status = self._check_specific_usb_camera_by_id()
        
        # Обновляем кэш
        self.usb_cache_status = status
        self.usb_cache_time = current_time
        
        return status

    def _check_specific_usb_camera_by_id(self):
        """Проверка конкретной USB-камеры по ID производителя и продукта (5843:7884)"""
        try:
            # Команда для поиска конкретной камеры по ID
            cmd = ['lsusb', '-d', '5843:7884']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0 and result.stdout.strip():
                # print(f"Найдена USB-камера по ID 5843:7884: {result.stdout.strip()}")
                return True
            return False
        except Exception as e:
            print(f"Ошибка при проверке камеры по ID: {e}")
            return False

    def check_scales(self):
        current_time = time.time()
        if self.scale_cache_status is not None and current_time - self.scale_cache_time < self.scale_cache_duration:
            return self.scale_cache_status
        
        devs = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        if not devs: 
            return False
        
        status = self._test_scale_connection(devs[0])
        self.scale_cache_status, self.scale_cache_time = status, current_time
        return status

    def _test_scale_connection(self, port):
        try:
            with serial.Serial(port, 9600, timeout=0.3) as ser:
                ser.write(b'\x05')
                time.sleep(0.1)
                return ser.read(1) == b'\x06'
        except Exception: 
            return False

    def check_microphone(self):
        try:
            res = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=2)
            return 'card' in res.stdout.lower() and 'usb audio' in res.stdout.lower()
        except Exception: 
            return False

    def check_speaker(self):
        try:
            res = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=2)
            return 'card' in res.stdout.lower() and 'usb audio' in res.stdout.lower()
        except Exception: 
            return False
