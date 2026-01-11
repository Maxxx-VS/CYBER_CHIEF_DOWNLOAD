# database.py

import time
import sqlite3
import os
from datetime import datetime
from sqlalchemy import text
from config import ID_POINT
import schedule_checker
from models import PeopleCounter, get_db_session

# Путь к локальной БД для буферизации
LOCAL_DB_PATH = 'offline_buffer.db'

def init_local_db():
    """Инициализация локальной SQLite БД для оффлайн хранения"""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS people_count_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                point_id INTEGER,
                record_datetime TEXT,
                record_date TEXT,
                record_hour INTEGER,
                count INTEGER
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка инициализации локальной БД: {e}")

def save_to_local_db(point_id, record_datetime, record_date, record_hour, count):
    """Сохранение в локальную БД при отсутствии связи"""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO people_count_buffer 
            (point_id, record_datetime, record_date, record_hour, count) 
            VALUES (?, ?, ?, ?, ?)
        ''', (point_id, str(record_datetime), str(record_date), record_hour, count))
        conn.commit()
        conn.close()
        # Убрали вывод успешного сохранения в локальный буфер, чтобы не спамить в лог
        # print(f"[OFFLINE] Данные сохранены локально: {count} чел.")
    except Exception as e:
        print(f"Критическая ошибка локального сохранения: {e}")

def sync_offline_data():
    """Синхронизация локальных данных с основной БД"""
    if not os.path.exists(LOCAL_DB_PATH):
        return

    # Читаем локальные данные
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM people_count_buffer')
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return

    if not rows:
        return

    print(f"Найдено {len(rows)} оффлайн записей. Попытка синхронизации...")
    
    session = get_db_session()
    if not session:
        return # Все еще нет связи

    ids_to_delete = []
    try:
        for row in rows:
            row_id, point_id, rec_dt_str, rec_date_str, rec_hour, count = row
            
            # Конвертация строк обратно в объекты даты
            rec_dt = datetime.fromisoformat(rec_dt_str)
            rec_date = datetime.strptime(rec_date_str, "%Y-%m-%d").date()

            people_record = PeopleCounter(
                id_точки=point_id,
                Дата_время_записи=rec_dt,
                Дата_записи=rec_date,
                Час_записи=rec_hour,
                Количество_людей=count
            )
            session.add(people_record)
            ids_to_delete.append(row_id)
        
        session.commit()
        print(f"Успешно синхронизировано {len(ids_to_delete)} записей.")

        # Очистка локальной БД после успешной отправки
        if ids_to_delete:
            conn = sqlite3.connect(LOCAL_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(f'DELETE FROM people_count_buffer WHERE id IN ({",".join(map(str, ids_to_delete))})')
            conn.commit()
            conn.close()

    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
        session.rollback()
    finally:
        session.close()

def save_people_count_to_db(people_count):
    """
    Сохраняет количество людей. 
    Алгоритм:
    1. Пробуем отправить оффлайн данные (если есть).
    2. Пробуем сохранить текущие данные в Postgres.
    3. Если ошибка (нет интернета) -> сохраняем в SQLite.
    """
    # 0. Подготовка данных
    current_time_gmt = time.gmtime()
    # Безопасное получение смещения (если schedule еще не загружен, берем 0)
    gmt_offset = schedule_checker.WORK_SCHEDULE.get('gmt_offset', 0)
    
    local_hour = (current_time_gmt.tm_hour + gmt_offset) % 24
    
    record_datetime = datetime(
        current_time_gmt.tm_year,
        current_time_gmt.tm_mon,
        current_time_gmt.tm_mday,
        local_hour, current_time_gmt.tm_min, current_time_gmt.tm_sec
    )
    record_date = record_datetime.date()
    
    # 1. Попытка синхронизации перед записью новых данных
    sync_offline_data()

    # 2. Попытка записи в основную БД
    session = None
    try:
        session = get_db_session()
        
        people_record = PeopleCounter(
            id_точки=ID_POINT,
            Дата_время_записи=record_datetime,
            Дата_записи=record_date,
            Час_записи=local_hour,
            Количество_людей=people_count
        )
        
        session.add(people_record)
        session.commit()
        
        # Убрали дублирующий вывод успешной отправки, так как данные уже в БД
        # print(f"Сохранено в БД: {people_count} человек(а) в {record_datetime}")
        
    except Exception as e:
        print(f"Ошибка подключения к БД ({e}). Переход в оффлайн режим.")
        if session:
            session.rollback()
            session.close()
        
        # 3. Сохранение в локальный буфер
        save_to_local_db(ID_POINT, record_datetime, record_date, local_hour, people_count)
        
    finally:
        if session:
            session.close()
