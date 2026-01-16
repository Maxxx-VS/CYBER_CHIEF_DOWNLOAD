import os
import ast
from pathlib import Path
from dotenv import load_dotenv

# Динамическое определение пути к .env файлу
current_dir = Path(__file__).parent
env_path = current_dir.parent / "enviroment" / ".env"

load_dotenv(dotenv_path=env_path, override=True)

# --- Глобальные переменные ---
WORK_SCHEDULE = {
    'start_time': os.getenv('TIME_COOK_IN'),
    'end_time': os.getenv('TIME_COOK_OUT'),
    'gmt_offset': 0
}
LAST_SCHEDULE_UPDATE = None

# --- Параметры приложения ---
RTSP_URL = os.getenv('RTSP_URL_COOK')
MODEL_PATH = os.getenv('MODEL_PATH')
HAT_GLOVE_MODEL_PATH = os.getenv('HAT_GLOVE_MODEL_PATH')

ID_POINT = int(os.getenv('POINT_ID'))

# Пороги уверенности
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD_COOK'))
HAT_GLOVE_CONFIDENCE_THRESHOLD = float(os.getenv('HAT_GLOVE_CONFIDENCE_THRESHOLD'))

SHOW_DETECTION = os.getenv('SHOW_DETECTION_COOK', 'False').lower() == 'true'
CAPTURE_INTERVAL = int(os.getenv('CAPTURE_INTERVAL_COOK'))
TIMEOUT_DURATION = int(os.getenv('TIMEOUT_DURATION_COOK'))

# --- Пороги нарушений ---
COUNT_VIOLATIONS = int(os.getenv('COUNT_VIOLATIONS'))
SOUND_PATH_WARNING = os.getenv('SOUND_PATH_WARNING')

# --- Параметры ROI ---
ROI_STRING = os.getenv('ROI_POINTS_COOK')
try:
    ROI = ast.literal_eval(ROI_STRING)
    if not isinstance(ROI, list) or not all(isinstance(point, list) and len(point) == 2 for point in ROI):
        raise ValueError("ROI должен быть списком точек [x, y]")
except Exception as e:
    print(f"Ошибка парсинга ROI: {e}. Используется значение по умолчанию.")
    ROI = [[0, 0], [640, 0], [640, 480], [0, 480]]

# --- Параметры ROI Table ---
ROI_TABLE_STRING = os.getenv('ROI_TABLE_POINTS_COOK')
try:
    ROI_TABLE = ast.literal_eval(ROI_TABLE_STRING)
    if not isinstance(ROI_TABLE, list) or not all(isinstance(point, list) and len(point) == 2 for point in ROI_TABLE):
        raise ValueError("ROI_TABLE должен быть списком точек [x, y]")
except Exception as e:
    print(f"Ошибка парсинга ROI_TABLE: {e}. ROI_TABLE не будет использоваться.")
    ROI_TABLE = None

# --- Параметры видеопотока ---
BUFFER_SIZE = int(os.getenv('CAMERA_BUFFER_SIZE'))
RECONNECT_TIMEOUT = int(os.getenv('CAMERA_RECONNECT_TIMEOUT'))
MAX_RECONNECT_ATTEMPTS = int(os.getenv('CAMERA_MAX_RECONNECT_ATTEMPTS'))

# --- Параметры ошибок декодирования ---
DECODE_ERROR_THRESHOLD = int(os.getenv('DECODE_ERROR_THRESHOLD', '10'))
DECODE_ERROR_WINDOW = int(os.getenv('DECODE_ERROR_WINDOW', '180'))
RECONNECT_ON_DECODE_ERROR = os.getenv('RECONNECT_ON_DECODE_ERROR', 'True').lower() == 'true'

# --- Настройки БД ---
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# === КОНФИГУРАЦИЯ СХЕМЫ БД (ORM MAPPING) ===
# Названия таблиц
DB_TABLE_TRADE_POINTS = os.getenv('DB_TABLE_TRADE_POINTS', 'С1_Торговые_точки')
DB_TABLE_CHEF_WORK = os.getenv('DB_TABLE_CHEF_WORK', 'CV_работа_повара')

# Столбцы таблицы торговых точек
DB_COL_POINT_ID = os.getenv('DB_COL_POINT_ID', 'id_точки')
DB_COL_GMT = os.getenv('DB_COL_GMT', 'GTM')

# Столбцы таблицы работы повара
DB_COL_WORK_START = os.getenv('DB_COL_WORK_START', 'Время_нач_работы')
DB_COL_WORK_END = os.getenv('DB_COL_WORK_END', 'Время_оконч_работы')
DB_COL_WORK_DURATION = os.getenv('DB_COL_WORK_DURATION', 'Продолж_работы')

# --- RAM диск ---
RAM_DISK_PATH = os.getenv('RAM_DISK_PATH')

# --- Директория для нарушений (Больше не используется для локального хранения, но оставим для совместимости) ---
VIOLATION_DIR = os.getenv('VIOLATION_DIR')

# --- SFTP Config ---
SFTP_URL = os.getenv('SFTP_URL')
SFTP_USER = os.getenv('SFTP_USER')
SFTP_PASSWORD = os.getenv('SFTP_PASSWORD')
# SFTP_PORT можно читать отдельно, но он также парсится из URL
SFTP_PORT = os.getenv('SFTP_PORT')
