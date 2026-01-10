import os
import time
import config

def setup_ram_disk():
    """
    Настройка RAM-диска.
    """
    path = config.RAM_DISK_PATH
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            print(f"Ошибка создания {path}: {e}")
    else:
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Ошибка очистки {file_path}: {e}")
    return path

def get_next_state_delay():
    """
    Рассчитывает текущее состояние (WORK/SLEEP) и количество секунд до следующего изменения состояния.
    Возвращает: ('WORK', seconds_left) или ('SLEEP', seconds_left)
    """
    schedule = config.WORK_SCHEDULE
    
    # Если расписания нет, считаем что нужно поспать минуту и попробовать снова
    if not schedule.get('start_time') or not schedule.get('end_time'):
        return 'SLEEP', 60
    
    try:
        current_time_gmt = time.gmtime()
        gmt_offset = schedule.get('gmt_offset', 0)
        
        # Текущее время в минутах от начала суток (с учетом GMT)
        current_hour = (current_time_gmt.tm_hour + gmt_offset + 24) % 24
        current_minutes_total = current_hour * 60 + current_time_gmt.tm_min
        current_seconds_offset = current_time_gmt.tm_sec 
        
        # Парсим начало и конец работы
        start_h, start_m = map(int, schedule['start_time'].split(':'))
        end_h, end_m = map(int, schedule['end_time'].split(':'))
        
        start_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m
        
        # Логика определения интервалов
        is_working_now = False
        next_event_minutes = 0
        
        if start_total <= end_total:
            # Дневная смена (например 09:00 - 18:00)
            if start_total <= current_minutes_total < end_total:
                is_working_now = True
                next_event_minutes = end_total - current_minutes_total
            elif current_minutes_total < start_total:
                is_working_now = False
                next_event_minutes = start_total - current_minutes_total
            else: # current > end
                is_working_now = False
                # До начала следующего дня
                next_event_minutes = (24 * 60 - current_minutes_total) + start_total
        else:
            # Ночная смена (например 22:00 - 06:00)
            if current_minutes_total >= start_total or current_minutes_total < end_total:
                is_working_now = True
                if current_minutes_total >= start_total:
                    # До полуночи + время до конца
                    next_event_minutes = (24 * 60 - current_minutes_total) + end_total
                else:
                    next_event_minutes = end_total - current_minutes_total
            else:
                is_working_now = False
                next_event_minutes = start_total - current_minutes_total
        
        # Переводим минуты в секунды и вычитаем текущие секунды для точности
        seconds_delay = max(1, (next_event_minutes * 60) - current_seconds_offset)
        
        return ('WORK' if is_working_now else 'SLEEP'), seconds_delay
            
    except Exception as e:
        print(f"Ошибка расчета времени: {e}")
        return 'SLEEP', 60
