import time
import sqlite3
import os
import shutil
from datetime import datetime
from sqlalchemy import create_engine, select, inspect, insert
from sqlalchemy.orm import sessionmaker

from config import (
    DATABASE_URL, ID_POINT, WORK_SCHEDULE, LAST_SCHEDULE_UPDATE,
    DB_TABLE_TRADE_POINTS, DB_COL_POINT_ID, DB_COL_GMT
)
from models import TradePoint, ChefWork
from sftp_client import SFTPUploader

# Настройка основной БД (Postgres)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'connect_timeout': 5})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Настройка локальной БД (SQLite)
LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_buffer.db')
OFFLINE_IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'offline_images')

def init_local_db():
    """Инициализация локального буфера"""
    if not os.path.exists(OFFLINE_IMG_DIR):
        os.makedirs(OFFLINE_IMG_DIR)
        
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    
    # Таблица для рабочих сессий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS work_session_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ts REAL,
            end_ts REAL,
            duration INTEGER
        )
    ''')
    
    # Таблица для нарушений (файлов)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violation_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_path TEXT,
            filename TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_local_db()

# --- Вспомогательные функции ---

def get_db_session():
    try:
        return SessionLocal()
    except Exception as e:
        print(f"Ошибка подключения к Postgres: {e}")
        return None

def get_gmt_offset():
    """
    Получение GMT смещения. Если нет связи, возвращает False.
    """
    global WORK_SCHEDULE, LAST_SCHEDULE_UPDATE
    
    session = get_db_session()
    if not session:
        return False
    
    try:
        # Используем имена из конфига или дефолтные
        # Примечание: Для ORM запросов лучше использовать атрибуты модели, 
        # но модель TradePoint уже определена.
        stmt = select(TradePoint.GTM).where(TradePoint.id_точки == ID_POINT)
        result = session.execute(stmt).scalar()
        
        if result is not None:
            WORK_SCHEDULE['gmt_offset'] = result
            LAST_SCHEDULE_UPDATE = time.time()
            print(f"Получено GMT смещение: {result} часов")
            return True
        else:
            print(f"Ошибка: Торговая точка с id={ID_POINT} не найдена")
            return False
    except Exception as e:
        print(f"Ошибка БД (GMT): {e}")
        return False
    finally:
        session.close()

def check_database_connection():
    """Проверка подключения"""
    try:
        with engine.connect() as connection:
            return True
    except Exception:
        return False

# --- Логика сохранения и синхронизации ---

def save_work_session_to_local(start_ts, end_ts, duration):
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO work_session_buffer (start_ts, end_ts, duration) VALUES (?, ?, ?)', 
                      (start_ts, end_ts, duration))
        conn.commit()
        conn.close()
        print(f"Saved locally (offline): Session {duration} min")
    except Exception as e:
        print(f"Local DB Error: {e}")

def save_violation_to_local(ram_path, filename):
    """Перемещает файл из RAM в постоянную папку и записывает в SQLite"""
    try:
        target_path = os.path.join(OFFLINE_IMG_DIR, filename)
        shutil.copy2(ram_path, target_path) # Copy instead of move initially to be safe
        
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO violation_buffer (local_path, filename) VALUES (?, ?)', 
                      (target_path, filename))
        conn.commit()
        conn.close()
        print(f"Saved locally (offline): Violation image {filename}")
        return True
    except Exception as e:
        print(f"Local DB Error (Violation): {e}")
        return False

def sync_offline_data():
    """Синхронизация данных при появлении интернета"""
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    
    # 1. Синхронизация сессий
    cursor.execute('SELECT id, start_ts, end_ts, duration FROM work_session_buffer')
    sessions = cursor.fetchall()
    
    if sessions:
        pg_session = get_db_session()
        if pg_session:
            print(f"Syncing {len(sessions)} offline sessions...")
            ids_to_del = []
            try:
                for row in sessions:
                    row_id, start_ts, end_ts, dur = row
                    
                    start_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_ts))
                    end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_ts))
                    
                    stmt = insert(ChefWork).values(
                        id_точки=ID_POINT,
                        Время_нач_работы=start_str,
                        Время_оконч_работы=end_str,
                        Продолж_работы=dur
                    )
                    pg_session.execute(stmt)
                    ids_to_del.append(row_id)
                
                pg_session.commit()
                if ids_to_del:
                    cursor.execute(f'DELETE FROM work_session_buffer WHERE id IN ({",".join(map(str, ids_to_del))})')
                    conn.commit()
                print("Sessions synced.")
            except Exception as e:
                print(f"Sync Error (Sessions): {e}")
                pg_session.rollback()
            finally:
                pg_session.close()

    # 2. Синхронизация нарушений (SFTP)
    cursor.execute('SELECT id, local_path, filename FROM violation_buffer')
    violations = cursor.fetchall()
    
    if violations:
        print(f"Syncing {len(violations)} offline violations...")
        uploader = SFTPUploader()
        # Проверяем связь SFTP простым способом (или доверяем upload_file)
        ids_to_del = []
        
        for row in violations:
            row_id, local_path, filename = row
            if os.path.exists(local_path):
                # Пытаемся загрузить
                if uploader.upload_file(local_path, filename):
                    ids_to_del.append(row_id)
                    # upload_file удаляет локальный файл, но мы передали путь из OFFLINE_IMG_DIR
                    # upload_file в sftp_client удаляет файл.
            else:
                # Файла нет, удаляем запись
                ids_to_del.append(row_id)
        
        if ids_to_del:
            cursor.execute(f'DELETE FROM violation_buffer WHERE id IN ({",".join(map(str, ids_to_del))})')
            conn.commit()
            print("Violations synced.")

    conn.close()

def save_work_session_to_db(start_time, end_time, duration_seconds):
    """
    Сохранение сессии. Сначала пробуем Postgres, если нет - SQLite.
    """
    duration_minutes = round(duration_seconds / 60)
    if duration_minutes <= 0:
        return False

    # Сначала пробуем синхронизироваться
    sync_offline_data()

    session = get_db_session()
    if not session:
        save_work_session_to_local(start_time, end_time, duration_minutes)
        return False

    try:
        start_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))
        end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))

        stmt = insert(ChefWork).values(
            id_точки=ID_POINT,
            Время_нач_работы=start_str,
            Время_оконч_работы=end_str,
            Продолж_работы=duration_minutes
        )
        session.execute(stmt)
        session.commit()
        print(f"Saved to DB: {duration_minutes} min")
        return True
    except Exception as e:
        print(f"Postgres Error: {e}. Switching to offline buffer.")
        session.rollback()
        save_work_session_to_local(start_time, end_time, duration_minutes)
        return False
    finally:
        session.close()
