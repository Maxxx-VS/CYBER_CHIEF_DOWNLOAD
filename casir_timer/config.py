import os
import ast
from dotenv import load_dotenv

# Загрузка переменных окружения
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, "..", "enviroment", ".env")
load_dotenv(dotenv_path=env_path)

# --- Основные настройки ---
ID_POINT = int(os.getenv('POINT_ID'))
RAM_DISK_PATH = os.getenv('RAM_DISK_PATH')

# --- Настройки камеры и потока ---
RTSP_URL = os.getenv('RTSP_URL_CASSIR')
BUFFER_SIZE = int(os.getenv('CAMERA_BUFFER_SIZE'))
RECONNECT_TIMEOUT = int(os.getenv('CAMERA_RECONNECT_TIMEOUT'))
MAX_RECONNECT_ATTEMPTS = int(os.getenv('CAMERA_MAX_RECONNECT_ATTEMPTS'))

# --- Настройки нейросети ---
MODEL_PATH = os.getenv('MODEL_PATH')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD_CASSIR'))
SHOW_DETECTION = os.getenv('SHOW_DETECTION_CASSIR').lower() == 'true'
CAPTURE_INTERVAL = int(os.getenv('CAPTURE_INTERVAL_CASSIR'))
TIMEOUT_DURATION = int(os.getenv('TIMEOUT_DURATION_CASSIR'))

# --- Настройки области интереса (ROI) ---
ROI_POINTS = os.getenv('ROI_POINTS_CASSIR')
ROI = None
try:
    if ROI_POINTS:
        parsed_roi = ast.literal_eval(ROI_POINTS)
        if isinstance(parsed_roi, list) and all(isinstance(p, list) and len(p) == 2 for p in parsed_roi):
            ROI = parsed_roi
        else:
            print("Предупреждение: Неверный формат ROI. Используется весь кадр.")
except (ValueError, SyntaxError):
    print("Предупреждение: Ошибка парсинга ROI. Используется весь кадр.")

# --- Настройки базы данных ---
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Формируем строку подключения для SQLAlchemy
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Глобальные переменные состояния ---
WORK_SCHEDULE = {
    'start_time': None,
    'end_time': None,
    'gmt_offset': 0
}
LAST_SCHEDULE_UPDATE = None
