# config.py
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Динамическое определение пути к .env файлу
current_file = Path(__file__).resolve()
project_root = current_file.parent
env_path = project_root.parent / "enviroment" / ".env"

load_dotenv(dotenv_path=env_path)

class Config:
    def __init__(self):
        # Весовые настройки
        self.WEIGHT_THRESHOLD = int(os.getenv('WEIGHT_THRESHOLD'))
        
        # Настройки TTS (Piper)
        self.WEIGHT_TTS_THRESHOLD = int(os.getenv('WEIGHT_TTS_THRESHOLD'))
        self.PIPER_BINARY_PATH = os.getenv('PIPER_BINARY_PATH')
        self.PIPER_MODEL_PATH = os.getenv('PIPER_MODEL_PATH')
        
        # Пути к директориям
        sound_dir = project_root.parent / "sound"
        
        # Имена аудиофайлов
        self.SOUND_PATH_PLUS = str(sound_dir / "plus.mp3")
        self.SOUND_PATH_MINUS = str(sound_dir / "minus.mp3")
        self.SOUND_PATH_VOSK = str(sound_dir / "vosk.mp3")
        self.SOUND_PATH_CAMERA = str(sound_dir / "camera.mp3")

        # Громкость (0-100%)
        self.VOLUME_LEVEL = os.getenv('VOLUME_LEVEL')
        
        # Vosk (Распознавание речи)
        self.MIC_GAIN = float(os.getenv('MIC_GAIN'))
        self.VOSK_MODEL_PATH = os.getenv('VOSK_MODEL_PATH')
        self.KEY_WORD = os.getenv('KEY_WORD').lower()
        
        # Настройки USB камеры
        self.USB_RESOLUTION = eval(os.getenv('USB_RESOLUTION'))
        self.FOCUS_DELAY = float(os.getenv('FOCUS_DELAY'))
        self.COOLDOWN_TIME = float(os.getenv('COOLDOWN_TIME'))
        
        # --- НАСТРОЙКИ КОРРЕКЦИИ ИЗОБРАЖЕНИЯ (DISTORSION) ---
        self.DIST_K1 = -1.0
        self.DIST_K2 = 1.0
        self.DIST_BALANCE = 1.0
        self.DIST_STRETCH_V = 1.5
        
        # YOLO settings
        self.YOLO_MODEL_PATH = os.getenv('YOLO_MODEL_PATH')
        self.YOLO_CONF_THRESH = float(os.getenv('YOLO_CONF_THRESH'))
        self.YOLO_CLASSES = [int(x) for x in os.getenv('YOLO_CLASSES').split(',')]
        
        # Настройки весов (USB)
        self.SCALE_PORT = os.getenv('SCALE_PORT')
        self.SCALE_BAUDRATE = int(os.getenv('SCALE_BAUDRATE'))
        
        # Настройки БД
        self.DB_WORK_HOST = os.getenv('DB_HOST')
        self.DB_WORK_PORT = os.getenv('DB_PORT')
        self.DB_WORK_NAME = os.getenv('DB_NAME')
        self.DB_WORK_USER = os.getenv('DB_USER')
        self.DB_WORK_PASSWORD = os.getenv('DB_PASSWORD')
        self.POINT_ID = int(os.getenv('POINT_ID'))
        
        # --- SFTP SETTINGS ---
        sftp_url = os.getenv('SFTP_URL')
        if ':' in sftp_url:
            self.SFTP_HOST, self.SFTP_PORT = sftp_url.split(':')
            self.SFTP_PORT = int(self.SFTP_PORT)
        else:
            self.SFTP_HOST = sftp_url
            self.SFTP_PORT = 22
            
        self.SFTP_USER = os.getenv('SFTP_USER')
        self.SFTP_PASSWORD = os.getenv('SFTP_PASSWORD')
        
        # Пути на SFTP сервере
        self.REMOTE_BASE_DIR = f"upload/detections/{self.POINT_ID}"
        self.REMOTE_DIR_USB = f"{self.REMOTE_BASE_DIR}/usb"
        self.REMOTE_DIR_YOLO = f"{self.REMOTE_BASE_DIR}/yolo"

        # --- RAM DISK CONFIGURATION ---
        # Получаем путь к RAM диску из .env или используем дефолтный линуксовый путь
        ram_disk_path_str = os.getenv('RAM_DISK_PATH')
        self.TEMP_DIR = Path(ram_disk_path_str)
        
        # Очищаем директорию в ОЗУ при старте (чтобы не забить память старыми файлами)
        if os.path.exists(self.TEMP_DIR):
            try:
                shutil.rmtree(self.TEMP_DIR)
            except Exception as e:
                print(f"Внимание: Не удалось очистить RAM папку {self.TEMP_DIR}: {e}")
        
        # Создаем папку в ОЗУ
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        
        # Перенаправляем сохранение фото во временную папку в ОЗУ
        # Camera и Detector будут писать сюда, думая что это обычный диск
        self.PHOTO_DIRS = {
            'usb': str(self.TEMP_DIR),
            'yolo': str(self.TEMP_DIR)
        }
