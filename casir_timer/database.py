import time
import sqlite3
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Импортируем модуль config
import config
from models import TradingPoint, CashierWork

# Локальная БД для буферизации
LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_buffer.db')

def init_local_db():
    """Инициализация локальной SQLite для хранения данных при отсутствии интернета"""
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS absence_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ts REAL,
            end_ts REAL,
            minutes INTEGER
        )
    ''')
    conn.commit()
    conn.close()

# Инициализируем локальную БД при импорте
init_local_db()

def get_db_session():
    """Создание сессии с перехватом ошибок подключения"""
    try:
        engine = create_engine(config.DATABASE_URL, connect_args={'connect_timeout': 5})
        Session = sessionmaker(bind=engine)
        return Session()
    except Exception as e:
        print(f"Нет подключения к основной БД: {e}")
        return None

def get_trading_point_schedule():
    """
    Получение времени работы. Если нет интернета - возвращает False.
    """
    session = get_db_session()
    if not session:
        return False

    try:
        point = session.query(TradingPoint).filter(TradingPoint.id_точки == config.ID_POINT).first()
        
        if point:
            config.WORK_SCHEDULE['start_time'] = point.ВремяС
            config.WORK_SCHEDULE['end_time'] = point.ВремяДо
            config.WORK_SCHEDULE['gmt_offset'] = point.GTM
            config.LAST_SCHEDULE_UPDATE = time.time()
            return True
        else:
            print(f"Ошибка: Торговая точка с id_точки={config.ID_POINT} не найдена")
            return False
            
    except Exception as e:
        print(f"Ошибка при получении данных из БД: {e}")
        return False
    finally:
        session.close()

def save_absence_to_local(start_ts, end_ts, minutes):
    """Сохранение в локальный буфер"""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO absence_buffer (start_ts, end_ts, minutes) VALUES (?, ?, ?)', 
                      (start_ts, end_ts, minutes))
        conn.commit()
        conn.close()
        print(f"Saved locally (offline): {minutes} min")
    except Exception as e:
        print(f"Critical local DB error: {e}")

def sync_offline_data():
    """Синхронизация локальных данных с основной БД"""
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, start_ts, end_ts, minutes FROM absence_buffer')
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return

    session = get_db_session()
    if not session:
        conn.close()
        return # Все еще нет интернета

    print(f"Attempting to sync {len(rows)} offline records...")
    ids_to_delete = []
    
    try:
        for row in rows:
            row_id, start_ts, end_ts, minutes = row
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt = datetime.fromtimestamp(end_ts)
            
            absence_record = CashierWork(
                id_точки=config.ID_POINT,
                Время_ухода_кассира=start_dt,
                Время_появления_кассира=end_dt,
                Время_отсутствия_кассира=minutes
            )
            session.add(absence_record)
            ids_to_delete.append(row_id)
        
        session.commit()
        
        # Удаляем отправленные записи из локальной БД
        if ids_to_delete:
            cursor.execute(f'DELETE FROM absence_buffer WHERE id IN ({",".join(map(str, ids_to_delete))})')
            conn.commit()
        print("Offline data synced successfully.")
        
    except Exception as e:
        print(f"Sync error: {e}")
        session.rollback()
    finally:
        session.close()
        conn.close()

def save_absence_to_db(start_time_ts, end_time_ts, absence_minutes):
    """
    Попытка сохранить в Postgres, при неудаче - в SQLite
    """
    # Сначала пробуем отправить локальные данные, если они есть
    sync_offline_data()

    session = get_db_session()
    if not session:
        save_absence_to_local(start_time_ts, end_time_ts, absence_minutes)
        return False

    try:
        start_dt = datetime.fromtimestamp(start_time_ts)
        end_dt = datetime.fromtimestamp(end_time_ts)
        
        absence_record = CashierWork(
            id_точки=config.ID_POINT,
            Время_ухода_кассира=start_dt,
            Время_появления_кассира=end_dt,
            Время_отсутствия_кассира=absence_minutes
        )
        
        session.add(absence_record)
        session.commit()
        print(f"Сохранено в БД: {start_dt} - {end_dt} ({absence_minutes} мин)")
        return True
        
    except Exception as e:
        print(f"Ошибка сохранения в Postgres: {e}. Switching to local buffer.")
        session.rollback()
        save_absence_to_local(start_time_ts, end_time_ts, absence_minutes)
        return False
    finally:
        if session:
            session.close()
