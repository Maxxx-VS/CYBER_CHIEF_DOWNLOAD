import os
import ast
from pathlib import Path
from dotenv import load_dotenv

# Определяем путь к .env файлу
current_dir = Path(__file__).parent
env_path = current_dir.parent / 'enviroment' / '.env'

# Загрузка переменных окружения
load_dotenv(env_path)

# --- Общие настройки ---
ID_POINT = int(os.getenv('POINT_ID', '1'))
RTSP_URL = os.getenv('RTSP_URL_CLIENT')  # Используем RTSP_URL_CLIENT

# Настройки подключения камеры
BUFFER_SIZE = int(os.getenv('CAMERA_BUFFER_SIZE', '1'))
RECONNECT_TIMEOUT = int(os.getenv('CAMERA_RECONNECT_TIMEOUT', '5'))
MAX_RECONNECT_ATTEMPTS = int(os.getenv('CAMERA_MAX_RECONNECT_ATTEMPTS', '10'))

# Модель
MODEL_PATH = os.getenv('MODEL_PATH', 'yolov8n.pt')

# --- Настройки Базы Данных ---
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'mydb')
DB_USER = os.getenv('DB_USER', 'user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')

# --- Настройки Мониторинга КАССИРА (Cashier) ---
CONFIDENCE_THRESHOLD_CASSIR = float(os.getenv('CONFIDENCE_THRESHOLD_CASSIR', '0.5'))
SHOW_DETECTION_CASSIR = os.getenv('SHOW_DETECTION_CASSIR', 'true').lower() == 'true'
CAPTURE_INTERVAL_CASSIR = int(os.getenv('CAPTURE_INTERVAL_CASSIR', '1'))
TIMEOUT_DURATION_CASSIR = int(os.getenv('TIMEOUT_DURATION_CASSIR', '300'))
ROI1_POINTS_STR = os.getenv('ROI_POINTS_CLI_CASSIR')  # Изменено на CLI_CASSIR

# --- Настройки Мониторинга КЛИЕНТА (Client) ---
CONFIDENCE_THRESHOLD_CLIENT = float(os.getenv('CONFIDENCE_THRESHOLD_CLIENT', '0.5'))
SHOW_DETECTION_CLIENT = os.getenv('SHOW_DETECTION_CLIENT', 'true').lower() == 'true'
CAPTURE_INTERVAL_CLIENT = int(os.getenv('CAPTURE_INTERVAL_CLIENT', '1'))
ROI2_POINTS_STR = os.getenv('ROI_POINTS_CLIENT')

# Таймеры логики клиента
CLIENT_APPEARANCE_TIMER = int(os.getenv('CLIENT_APPEARANCE_TIMER', '30'))
CLIENT_DEPARTURE_TIMER = int(os.getenv('CLIENT_DEPARTURE_TIMER', '10'))
CASHIER_WAIT_TIMER = int(os.getenv('CASHIER_WAIT_TIMER', '60'))

# --- Глобальные переменные состояния ---
WORK_SCHEDULE = {
    'start_time': None,
    'end_time': None,
    'gmt_offset': 0
}
LAST_SCHEDULE_UPDATE = None

# --- Обработка ROI ---
def parse_roi_points(roi_string):
    """Парсинг строки с точками ROI"""
    if not roi_string:
        return None
    try:
        roi = ast.literal_eval(roi_string)
        if isinstance(roi, list) and all(isinstance(point, list) and len(point) == 2 for point in roi):
            return roi
        return None
    except (ValueError, SyntaxError):
        return None

ROI1 = parse_roi_points(ROI1_POINTS_STR)  # Кассир (ROI_POINTS_CLI_CASSIR)
ROI2 = parse_roi_points(ROI2_POINTS_STR)  # Клиент (ROI_POINTS_CLIENT)

# Список всех ROI: [0] - Кассир, [1] - Клиент
ROI_LIST = []
if ROI1 is not None:
    ROI_LIST.append(ROI1)
if ROI2 is not None:
    ROI_LIST.append(ROI2)

if not ROI_LIST:
    ROI_LIST = None
    print("Предупреждение: Не заданы ROI. Используется весь кадр.")

# Для обратной совместимости (оставляем для старых вызовов)
CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD_CASSIR 
SHOW_DETECTION = SHOW_DETECTION_CASSIR
CAPTURE_INTERVAL = CAPTURE_INTERVAL_CASSIR
TIMEOUT_DURATION = TIMEOUT_DURATION_CASSIR

if __name__ == "__main__":
    print("\nТекущие настройки:")
    print(f"ID_POINT: {ID_POINT}")
    print(f"RTSP_URL: {RTSP_URL[:50]}..." if RTSP_URL and len(RTSP_URL) > 50 else f"RTSP_URL: {RTSP_URL}")
    print(f"ROI кассира: {'Задан' if ROI1 else 'Не задан'}")
    print(f"ROI клиента: {'Задан' if ROI2 else 'Не задан'}")
    print(f"ROI_LIST len: {len(ROI_LIST) if ROI_LIST else 0}")
    print(f"DB_HOST: {DB_HOST}")
    print(f"DB_PORT: {DB_PORT}")
    print(f"DB_NAME: {DB_NAME}")
