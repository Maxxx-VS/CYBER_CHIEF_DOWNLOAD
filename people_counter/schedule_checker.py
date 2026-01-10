# schedule_checker.py

import time
from datetime import datetime, timedelta
from config import ID_POINT
from models import TradingPoint, get_db_session

WORK_SCHEDULE = {
    'start_time': None,
    'end_time': None,
    'gmt_offset': 0
}
LAST_SCHEDULE_UPDATE = None

def get_trading_point_schedule():
    """
    Получение времени работы.
    Возвращает False, если не удалось подключиться к БД.
    """
    global WORK_SCHEDULE, LAST_SCHEDULE_UPDATE
    
    session = None
    try:
        session = get_db_session()
        # Пробуем выполнить простой запрос для проверки связи, так как создание session ленивое
        trading_point = session.query(TradingPoint).filter(
            TradingPoint.id_точки == ID_POINT
        ).first()
        
        if trading_point:
            WORK_SCHEDULE['start_time'] = trading_point.ВремяС
            WORK_SCHEDULE['end_time'] = trading_point.ВремяДо
            WORK_SCHEDULE['gmt_offset'] = trading_point.GTM
            LAST_SCHEDULE_UPDATE = time.time()
            
            print(f"Расписание обновлено: {WORK_SCHEDULE['start_time']} - {WORK_SCHEDULE['end_time']} (GMT+{WORK_SCHEDULE['gmt_offset']})")
            return True
        else:
            print(f"Ошибка: Точка ID={ID_POINT} не найдена в БД.")
            return False
            
    except Exception as e:
        print(f"Ошибка получения расписания (DB Error): {e}")
        return False
        
    finally:
        if session:
            session.close()

def calculate_next_change_time():
    """
    Рассчитывает время до следующего события.
    Логика использует таймер, а не polling.
    """
    # Если расписания нет, возвращаем короткий интервал сна, чтобы основной цикл попробовал обновить расписание
    if not WORK_SCHEDULE['start_time'] or not WORK_SCHEDULE['end_time']:
        return 60, True # Спим 60 сек, потом снова пытаемся получить расписание
    
    try:
        current_time_gmt = time.gmtime()
        current_hour = current_time_gmt.tm_hour + WORK_SCHEDULE['gmt_offset']
        current_minute = current_time_gmt.tm_min
        current_second = current_time_gmt.tm_sec
        
        # Нормализация часов (0-23)
        current_hour = (current_hour + 24) % 24
        
        current_total_seconds = current_hour * 3600 + current_minute * 60 + current_second
        
        start_h, start_m = map(int, WORK_SCHEDULE['start_time'].split(':'))
        end_h, end_m = map(int, WORK_SCHEDULE['end_time'].split(':'))
        
        start_total = start_h * 3600 + start_m * 60
        end_total = end_h * 3600 + end_m * 60
        
        is_active = False
        
        # Определение текущего статуса
        if start_total <= end_total:
            # Смена внутри одного дня (например, 09:00 - 21:00)
            is_active = start_total <= current_total_seconds < end_total
        else:
            # Смена через полночь (например, 22:00 - 06:00)
            is_active = (current_total_seconds >= start_total) or (current_total_seconds < end_total)
        
        seconds_to_change = 0
        
        if is_active:
            # СЕЙЧАС РАБОТАЕМ. Считаем время до КОНЦА смены.
            next_status_is_work = False
            
            if current_total_seconds < end_total:
                seconds_to_change = end_total - current_total_seconds
            else:
                # Для ночной смены, если сейчас время до полуночи, а конец смены завтра
                seconds_to_change = (86400 - current_total_seconds) + end_total
        else:
            # СЕЙЧАС ОТДЫХАЕМ. Считаем время до НАЧАЛА смены.
            next_status_is_work = True
            
            if current_total_seconds < start_total:
                seconds_to_change = start_total - current_total_seconds
            else:
                # Начало смены уже завтра
                seconds_to_change = (86400 - current_total_seconds) + start_total
        
        # Защита от отрицательных значений
        return max(1, seconds_to_change), next_status_is_work
        
    except Exception as e:
        print(f"Ошибка расчета таймера: {e}")
        return 60, True # Аварийный сон 1 минута
