import os
from pathlib import Path
from dotenv import load_dotenv

# Определяем путь к .env файлу относительно текущего файла config.py
current_dir = Path(__file__).parent
env_path = current_dir.parent / 'enviroment' / '.env'

# Загрузка переменных окружения из .env файла
load_dotenv(env_path)

# Настройки базы данных
ID_POINT = int(os.getenv('POINT_ID'))
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT'))
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Настройки камеры
RTSP_URL = os.getenv('RTSP_URL_PEOPLE')
CAMERA_WIDTH = int(os.getenv('CAMERA_WIDTH'))
CAMERA_HEIGHT = int(os.getenv('CAMERA_HEIGHT'))
CAMERA_FPS = int(os.getenv('CAMERA_FPS'))

# Настройки приложения
BUFFER_SIZE = int(os.getenv('CAMERA_BUFFER_SIZE'))
RECONNECT_TIMEOUT = int(os.getenv('CAMERA_RECONNECT_TIMEOUT'))
MAX_RECONNECT_ATTEMPTS = int(os.getenv('CAMERA_MAX_RECONNECT_ATTEMPTS'))
HEALTH_CHECK_INTERVAL = float(os.getenv('HEALTH_CHECK_INTERVAL'))
REPORT_INTERVAL = float(os.getenv('REPORT_INTERVAL'))
MODEL_PATH = os.getenv('MODEL_PATH_VIDEO')
SHOW_WINDOW = os.getenv('SHOW_DETECTION_PEOPLE').lower() == 'true'
TARGET_DETECTION_FPS = int(os.getenv('TARGET_FPS'))
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD'))

# Настройки ROI
ROI_STR = os.getenv('ROI_POINTS_PEOPLE')

# Выводим информацию о загруженном .env файле для отладки
print(f"Загружен .env файл из: {env_path}")
