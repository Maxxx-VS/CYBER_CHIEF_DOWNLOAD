# database.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import Config
from models import RollCount

config = Config()

engine = None
SessionLocal = None
db_available = False

def init_db():
    """
    Инициализирует подключение к БД.
    Возвращает True, если успешно, иначе False.
    """
    global engine, SessionLocal, db_available
    
    # [FIX] Явное закрытие старого engine перед пересозданием
    # Это предотвращает утечку соединений при частых реконнектах
    if engine:
        try:
            engine.dispose()
        except Exception:
            pass
    
    try:
        db_url = f"postgresql://{config.DB_WORK_USER}:{config.DB_WORK_PASSWORD}@{config.DB_WORK_HOST}:{config.DB_WORK_PORT}/{config.DB_WORK_NAME}"
        engine = create_engine(db_url, pool_pre_ping=True)
        
        # Проверка соединения
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_available = True
        return True
        
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        db_available = False
        return False

def get_session():
    """Создает новую сессию, если БД доступна."""
    if db_available and SessionLocal:
        return SessionLocal()
    return None

def save_roll_count(point_id, timestamp, hour, weight_count, detection_count, max_weight, max_detection, mass=None):
    """
    Сохраняет запись в БД с безопасным управлением сессией.
    """
    # Фильтр пустых записей (если все по нулям, запись не идет в БД)
    if weight_count == 0 and detection_count == 0 and max_weight == 0 and max_detection == 0 and (mass is None or mass == 0):
        return True
    
    if not db_available:
        if not init_db():
            return False
        
    session = get_session()
    if not session:
        return False

    try:
        timestamp = timestamp.replace(microsecond=0)
        
        record = RollCount(
            point_id=point_id,
            timestamp=timestamp,
            hour=hour,
            count_weight=weight_count,
            count_detection=detection_count,
            max_count_weight=max_weight,
            max_count_detection=max_detection,
            mass=mass
        )
        
        session.add(record)
        session.commit()
        return True
            
    except Exception as e:
        session.rollback()
        print(f"Ошибка при сохранении в БД: {e}")
        
        # Пытаемся переподключиться при ошибке
        init_db()
        return False
        
    finally:
        session.close()
