import time
from config import WORK_SCHEDULE

def calculate_next_change():
    """
    Рассчитывает текущее состояние и время до следующего изменения.
    Возвращает: (is_working_now, seconds_until_change)
    """
    if not WORK_SCHEDULE['start_time'] or not WORK_SCHEDULE['end_time']:
        # Если расписания нет, работаем по умолчанию или спим минуту
        return False, 60

    try:
        current_time_gmt = time.gmtime()
        gmt_offset = WORK_SCHEDULE.get('gmt_offset', 0)
        
        # Текущее время в секундах от начала суток
        current_hour = (current_time_gmt.tm_hour + gmt_offset + 24) % 24
        current_total_seconds = current_hour * 3600 + current_time_gmt.tm_min * 60 + current_time_gmt.tm_sec
        
        start_h, start_m = map(int, WORK_SCHEDULE['start_time'].split(':'))
        end_h, end_m = map(int, WORK_SCHEDULE['end_time'].split(':'))
        
        start_total = start_h * 3600 + start_m * 60
        end_total = end_h * 3600 + end_m * 60
        
        is_working = False
        wait_seconds = 0
        
        if start_total <= end_total:
            # Смена внутри одного дня (09:00 - 18:00)
            if start_total <= current_total_seconds < end_total:
                is_working = True
                wait_seconds = end_total - current_total_seconds
            elif current_total_seconds < start_total:
                is_working = False
                wait_seconds = start_total - current_total_seconds
            else:
                is_working = False
                wait_seconds = (86400 - current_total_seconds) + start_total
        else:
            # Ночная смена (22:00 - 06:00)
            if current_total_seconds >= start_total or current_total_seconds < end_total:
                is_working = True
                if current_total_seconds >= start_total:
                    wait_seconds = (86400 - current_total_seconds) + end_total
                else:
                    wait_seconds = end_total - current_total_seconds
            else:
                is_working = False
                wait_seconds = start_total - current_total_seconds
                
        return is_working, max(1, wait_seconds)
        
    except Exception as e:
        print(f"Ошибка расчета расписания: {e}")
        return False, 60

def should_monitoring_be_active():
    """Совместимость со старым кодом"""
    is_active, _ = calculate_next_change()
    return is_active

def get_next_state_delay():
    """Возвращает ('WORK', duration) или ('SLEEP', duration)"""
    is_working, seconds = calculate_next_change()
    state = 'WORK' if is_working else 'SLEEP'
    return state, seconds
