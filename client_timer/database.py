import time
import sqlite3
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Импорт моделей
from models import Base, TradingPoint, CashierWork, ClientPresence
from config import (
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, 
    ID_POINT, WORK_SCHEDULE, LAST_SCHEDULE_UPDATE
)

# --- Настройка локальной БД для оффлайн режима ---
LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_buffer.db')

def init_local_db():
    """Инициализация локальной SQLite для хранения данных при отсутствии интернета"""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        # Таблица для кассира
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS absence_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_ts REAL,
                end_ts REAL,
                minutes INTEGER
            )
        ''')
        # Таблица для клиента
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appearance_ts REAL,
                departure_ts REAL,
                wait_minutes INTEGER
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка инициализации локальной БД: {e}")

init_local_db()
# ------------------------------------------------

# Сборка URL подключения внутри модуля
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'connect_timeout': 5})
    SessionFactory = sessionmaker(bind=engine)
    Session = scoped_session(SessionFactory)
except Exception as e:
    print(f"Ошибка создания engine SQLAlchemy: {e}")
    Session = None

def get_db_session():
    """Контекстный менеджер для получения сессии"""
    if Session is None:
        return None
    try:
        return Session()
    except Exception as e:
        print(f"Ошибка создания сессии БД: {e}")
        return None

def get_trading_point_schedule():
    """
    Получение времени работы торговой точки. 
    Возвращает False, если нет связи с БД.
    """
    # Используем словарь из config напрямую (он изменяемый)
    global WORK_SCHEDULE
    
    session = get_db_session()
    if not session:
        return False

    try:
        point = session.query(TradingPoint).filter(TradingPoint.id_точки == ID_POINT).first()
        
        if point:
            WORK_SCHEDULE['start_time'] = point.ВремяС
            WORK_SCHEDULE['end_time'] = point.ВремяДо
            WORK_SCHEDULE['gmt_offset'] = point.GTM
            
            # Обновляем переменную в config (т.к. она там импортирована, изменения отразятся)
            import config
            config.LAST_SCHEDULE_UPDATE = time.time()
            return True
        else:
            print(f"Ошибка: Торговая точка с id_точки={ID_POINT} не найдена")
            return False
            
    except Exception as e:
        print(f"Ошибка при получении расписания (Postgres): {e}")
        return False
    finally:
        if Session:
            Session.remove()

# --- Функции локального сохранения ---

def save_client_to_local(app_ts, dep_ts, minutes):
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO client_buffer (appearance_ts, departure_ts, wait_minutes) VALUES (?, ?, ?)', 
                      (app_ts, dep_ts, minutes))
        conn.commit()
        conn.close()
        print(f"Saved locally (offline) - Client wait: {minutes} min")
    except Exception as e:
        print(f"Local DB error: {e}")

def save_absence_to_local(start_ts, end_ts, minutes):
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO absence_buffer (start_ts, end_ts, minutes) VALUES (?, ?, ?)', 
                      (start_ts, end_ts, minutes))
        conn.commit()
        conn.close()
        print(f"Saved locally (offline) - Cashier absence: {minutes} min")
    except Exception as e:
        print(f"Local DB error: {e}")

# --- Синхронизация ---

def sync_offline_data():
    """Отправка накопленных данных в основную БД"""
    if not os.path.exists(LOCAL_DB_PATH):
        return

    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        
        # 1. Синхронизация клиентов
        cursor.execute('SELECT id, appearance_ts, departure_ts, wait_minutes FROM client_buffer')
        client_rows = cursor.fetchall()
        
        # 2. Синхронизация кассиров
        cursor.execute('SELECT id, start_ts, end_ts, minutes FROM absence_buffer')
        cashier_rows = cursor.fetchall()
        
        if not client_rows and not cashier_rows:
            conn.close()
            return

        session = get_db_session()
        if not session:
            conn.close()
            return # Нет интернета

        print(f"Syncing offline data: {len(client_rows)} clients, {len(cashier_rows)} cashier records...")
        
        # Обработка клиентов
        client_ids_to_del = []
        for row in client_rows:
            rid, app_ts, dep_ts, minutes = row
            rec = ClientPresence(
                id_точки=ID_POINT,
                Время_появления_клиента=datetime.fromtimestamp(app_ts),
                Время_ухода_клиента=datetime.fromtimestamp(dep_ts),
                Время_ожидания_клиента=minutes
            )
            session.add(rec)
            client_ids_to_del.append(rid)

        # Обработка кассиров
        cashier_ids_to_del = []
        for row in cashier_rows:
            rid, start_ts, end_ts, minutes = row
            rec = CashierWork(
                id_точки=ID_POINT,
                Время_ухода_кассира=datetime.fromtimestamp(start_ts),
                Время_появления_кассира=datetime.fromtimestamp(end_ts),
                Время_отсутствия_кассира=minutes
            )
            session.add(rec)
            cashier_ids_to_del.append(rid)

        session.commit()
        
        # Удаление из локальной БД
        if client_ids_to_del:
            cursor.execute(f'DELETE FROM client_buffer WHERE id IN ({",".join(map(str, client_ids_to_del))})')
        if cashier_ids_to_del:
            cursor.execute(f'DELETE FROM absence_buffer WHERE id IN ({",".join(map(str, cashier_ids_to_del))})')
        
        conn.commit()
        print("Offline data synced.")
        conn.close()

    except Exception as e:
        print(f"Sync error: {e}")
        if 'session' in locals() and session:
            session.rollback()
    finally:
        if Session:
            Session.remove()

# --- Публичные функции сохранения ---

def save_absence_to_db(start_time, end_time, absence_minutes):
    sync_offline_data() # Пробуем синхронизироваться перед новой записью
    
    session = get_db_session()
    if not session:
        save_absence_to_local(start_time, end_time, absence_minutes)
        return False

    try:
        dt_start = datetime.fromtimestamp(start_time)
        dt_end = datetime.fromtimestamp(end_time)
        new_record = CashierWork(
            id_точки=ID_POINT,
            Время_ухода_кассира=dt_start,
            Время_появления_кассира=dt_end,
            Время_отсутствия_кассира=absence_minutes
        )
        session.add(new_record)
        session.commit()
        print(f"Сохранено в БД (Кассир): {absence_minutes} мин")
        return True
    except Exception as e:
        print(f"DB Error (Cashier): {e}. Saving locally.")
        session.rollback()
        save_absence_to_local(start_time, end_time, absence_minutes)
        return False
    finally:
        if Session:
            Session.remove()

def save_client_presence_to_db(appearance_time, departure_time, wait_minutes):
    sync_offline_data()
    
    session = get_db_session()
    if not session:
        save_client_to_local(appearance_time, departure_time, wait_minutes)
        return False

    try:
        dt_appearance = datetime.fromtimestamp(appearance_time)
        dt_departure = datetime.fromtimestamp(departure_time)
        new_record = ClientPresence(
            id_точки=ID_POINT,
            Время_появления_клиента=dt_appearance,
            Время_ухода_клиента=dt_departure,
            Время_ожидания_клиента=wait_minutes
        )
        session.add(new_record)
        session.commit()
        print(f"Сохранено в БД (Клиент): {wait_minutes} мин")
        return True
    except Exception as e:
        print(f"DB Error (Client): {e}. Saving locally.")
        session.rollback()
        save_client_to_local(appearance_time, departure_time, wait_minutes)
        return False
    finally:
        if Session:
            Session.remove()
