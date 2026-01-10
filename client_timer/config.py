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
ID_POINT = int(os.getenv('POINT_ID'))
# Внимание: client_timer.py использует RTSP_URL_CLIENT, хотя логически это мониторинг кассира.
# Оставляем как есть, чтобы не сломать подключение, если камеры разные.
RTSP_URL = os.getenv('RTSP_URL_CLIENT') 

# Настройки подключения камеры
BUFFER_SIZE = int(os.getenv('CAMERA_BUFFER_SIZE'))
RECONNECT_TIMEOUT = int(os.getenv('CAMERA_RECONNECT_TIMEOUT'))
MAX_RECONNECT_ATTEMPTS = int(os.getenv('CAMERA_MAX_RECONNECT_ATTEMPTS'))

# Модель
MODEL_PATH = os.getenv('MODEL_PATH')

# --- Настройки Базы Данных ---
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT'))
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# --- Настройки Мониторинга КАССИРА (Cashier) ---
CONFIDENCE_THRESHOLD_CASSIR = float(os.getenv('CONFIDENCE_THRESHOLD_CASSIR'))
SHOW_DETECTION_CASSIR = os.getenv('SHOW_DETECTION_CASSIR').lower() == 'true'
CAPTURE_INTERVAL_CASSIR = int(os.getenv('CAPTURE_INTERVAL_CASSIR'))
TIMEOUT_DURATION_CASSIR = int(os.getenv('TIMEOUT_DURATION_CASSIR'))
ROI1_POINTS_STR = os.getenv('ROI_POINTS_CASSIR')

# --- Настройки Мониторинга КЛИЕНТА (Client) ---
CONFIDENCE_THRESHOLD_CLIENT = float(os.getenv('CONFIDENCE_THRESHOLD_CLIENT'))
SHOW_DETECTION_CLIENT = os.getenv('SHOW_DETECTION_CLIENT').lower() == 'true'
CAPTURE_INTERVAL_CLIENT = int(os.getenv('CAPTURE_INTERVAL_CLIENT'))
ROI2_POINTS_STR = os.getenv('ROI_POINTS_CLIENT')

# Таймеры логики клиента
CLIENT_APPEARANCE_TIMER = int(os.getenv('CLIENT_APPEARANCE_TIMER'))
CLIENT_DEPARTURE_TIMER = int(os.getenv('CLIENT_DEPARTURE_TIMER'))
CASHIER_WAIT_TIMER = int(os.getenv('CASHIER_WAIT_TIMER'))

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

ROI1 = parse_roi_points(ROI1_POINTS_STR)
ROI2 = parse_roi_points(ROI2_POINTS_STR)

# Список всех ROI: [0] - Кассир, [1] - Клиент
ROI_LIST = []
if ROI1 is not None:
    ROI_LIST.append(ROI1)
if ROI2 is not None:
    ROI_LIST.append(ROI2)

if not ROI_LIST:
    ROI_LIST = None
    print("Предупреждение: Не заданы ROI. Используется весь кадр.")

# Для обратной совместимости с client_timer.py (если не менять имена переменных в скрипте)
# Но мы обновим скрипт, чтобы использовать специфичные переменные.
CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD_CASSIR 
SHOW_DETECTION = SHOW_DETECTION_CASSIR
CAPTURE_INTERVAL = CAPTURE_INTERVAL_CASSIR
TIMEOUT_DURATION = TIMEOUT_DURATION_CASSIR

if __name__ == "__main__":
    print("\nТекущие настройки:")
    print(f"ID_POINT: {ID_POINT}")
    print(f"RTSP_URL: {RTSP_URL[:50]}...")
    print(f"ROI_LIST len: {len(ROI_LIST) if ROI_LIST else 0}")
    print(f"DB_HOST: {DB_HOST}")
