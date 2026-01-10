# camera.py
import cv2
import os
import glob
import subprocess
from image_processor import ImageCorrector

class USBCamera:
    def __init__(self, config):
        self.config = config
        self.device_path = None
        self.cap = None
        self.corrector = None  # Инициализируем корректор
        
        self._find_camera()
        self._setup_camera()
        
        # Инициализация корректора изображения, если камера найдена
        if self.config.USB_RESOLUTION:
            w, h = self.config.USB_RESOLUTION
            self.corrector = ImageCorrector(w, h, self.config)

    def _find_camera(self):
        try:
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True,
                text=True,
                check=True
            )
            devices = []
            current_device = ""
            
            for line in result.stdout.split('\n'):
                if line.strip() and not line.startswith('\t'):
                    current_device = line.strip()
                elif '/dev/video' in line:
                    path = line.strip()
                    devices.append((current_device, path))
            
            for name, path in devices:
                if 'usb' in name.lower():
                    self.device_path = path
                    return
            
            if devices:
                self.device_path = devices[0][1]
                return
                
        except Exception as e:
            pass
        
        try:
            video_devices = glob.glob('/dev/video*')
            if video_devices:
                self.device_path = video_devices[0]
        except Exception as e:
            pass

    def _setup_camera(self):
        if not self.device_path:
            return
            
        try:
            self.cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
            
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.device_path)
            
            if not self.cap.isOpened():
                return
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.USB_RESOLUTION[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.USB_RESOLUTION[1])
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            
        except Exception as e:
            return

    def capture(self, file_path):
        if not self.cap or not self.cap.isOpened():
            return False
            
        try:
            # Считываем несколько кадров для очистки буфера
            for _ in range(5):
                ret, frame = self.cap.read()
            
            if ret and frame is not None:
                # --- ИНТЕГРАЦИЯ ИСПРАВЛЕНИЯ ИСКАЖЕНИЙ ---
                if self.corrector:
                    frame = self.corrector.process(frame)
                # ----------------------------------------
                
                success = cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if success:
                    return True
                else:
                    return False
            else:
                return False
        except Exception as e:
            print(f"Ошибка захвата: {e}")
            return False

    def reconnect(self):
        if self.cap:
            self.cap.release()
        self._setup_camera()
