import os
from pathlib import Path
from dotenv import load_dotenv

current_dir = Path(__file__).parent
env_path = current_dir.parent / "enviroment" / ".env"
load_dotenv(dotenv_path=env_path)

class Config:
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT')
    DB_NAME = os.getenv('DB_NAME')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    POINT_ID = int(os.getenv('POINT_ID'))
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 20))
    BASE_DIR = os.path.expanduser('~/cyber_chief/people_counter')
    SRC_DIR = os.path.join(BASE_DIR, 'src')
    RTSP_URL_COOK = os.getenv('RTSP_URL_COOK')
    RTSP_URL_CASSIR = os.getenv('RTSP_URL_CASSIR')
    RTSP_URL_CLIENT = os.getenv('RTSP_URL_CLIENT')
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
