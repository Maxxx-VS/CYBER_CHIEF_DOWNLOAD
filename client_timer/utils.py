import os
import time
import tempfile
from config import WORK_SCHEDULE

def setup_ram_disk(prefix="monitor"):
    """
    Настройка временного каталога в памяти с префиксом для разделения потоков
    """
    # Пытаемся использовать /dev/shm для Linux
    if os.path.exists("/dev/shm"):
        ram_disk_path = f"/dev/shm/{prefix}_cashier_monitor_{os.getpid()}_{int(time.time())}"
    else:
        # Fallback для других систем
        ram_disk_path = os.path.join(tempfile.gettempdir(), f"{prefix}_cashier_monitor_{os.getpid()}_{int(time.time())}")
    
    try:
        os.makedirs(ram_disk_path, exist_ok=True)
        # Очищаем каталог на всякий случай
        for filename in os.listdir(ram_disk_path):
            file_path = os.path.join(ram_disk_path, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Ошибка при удалении {file_path}: {e}")
    except Exception as e:
        print(f"Ошибка при создании временного каталога: {e}")
        # Последний fallback
        ram_disk_path = f"./temp_{prefix}_{os.getpid()}"
        os.makedirs(ram_disk_path, exist_ok=True)
    
    return ram_disk_path

def calculate_next_schedule_change():
    """
    Рассчитывает время до следующего изменения статуса (рабочее/нерабочее время)
    Возвращает: (is_active_now, seconds_until_next_change)
    """
    if not WORK_SCHEDULE['start_time'] or not WORK_SCHEDULE['end_time']:
        return False, 60  # Если расписания нет, проверяем через минуту
    
    try:
        # Получаем текущее время в GMT
        current_time_gmt = time.gmtime()
        gmt_offset = WORK_SCHEDULE.get('gmt_offset', 0)
        
        # Текущее время в секундах от начала дня с учетом GMT offset
        current_hour = (current_time_gmt.tm_hour + gmt_offset) % 24
        current_total_seconds = current_hour * 3600 + current_time_gmt.tm_min * 60 + current_time_gmt.tm_sec
        
        # Парсим время начала и окончания работы
        start_h, start_m = map(int, WORK_SCHEDULE['start_time'].split(':'))
        end_h, end_m = map(int, WORK_SCHEDULE['end_time'].split(':'))
        
        start_total_seconds = start_h * 3600 + start_m * 60
        end_total_seconds = end_h * 3600 + end_m * 60
        
        is_active_now = False
        seconds_until_change = 0
        
        if start_total_seconds <= end_total_seconds:
            # Дневная смена (в течение одного дня)
            if start_total_seconds <= current_total_seconds < end_total_seconds:
                is_active_now = True
                seconds_until_change = end_total_seconds - current_total_seconds
            elif current_total_seconds < start_total_seconds:
                is_active_now = False
                seconds_until_change = start_total_seconds - current_total_seconds
            else:
                is_active_now = False
                seconds_until_change = (86400 - current_total_seconds) + start_total_seconds
        else:
            # Ночная смена (переход через полночь)
            if current_total_seconds >= start_total_seconds or current_total_seconds < end_total_seconds:
                is_active_now = True
                if current_total_seconds >= start_total_seconds:
                    seconds_until_change = (86400 - current_total_seconds) + end_total_seconds
                else:
                    seconds_until_change = end_total_seconds - current_total_seconds
            else:
                is_active_now = False
                seconds_until_change = start_total_seconds - current_total_seconds
                
        return is_active_now, max(1, seconds_until_change)
        
    except Exception as e:
        print(f"Ошибка при расчете времени: {e}")
        return False, 60

def should_monitoring_be_active():
    """Совместимость со старым кодом"""
    is_active, _ = calculate_next_schedule_change()
    return is_active

def get_sleep_until_next_change():
    """Возвращает количество секунд до следующего изменения статуса"""
    _, seconds = calculate_next_schedule_change()
    return seconds

def get_next_state_delay():
    """
    Удобная обертка для главного цикла.
    Возвращает ('WORK', duration) или ('SLEEP', duration)
    """
    is_active, seconds = calculate_next_schedule_change()
    return ('WORK' if is_active else 'SLEEP'), seconds
