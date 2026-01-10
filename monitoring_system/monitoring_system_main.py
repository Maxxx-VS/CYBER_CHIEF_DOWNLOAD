#!/usr/bin/env python3
import os
import time
from datetime import datetime # Убрали timezone, timedelta
from monitoring_system_config import Config
from monitoring_system_database import DatabaseManager
from monitoring_system_checker import CameraChecker


def get_cpu_temp():
    """Функция для получения температуры CPU"""
    try:
        temp = os.popen("vcgencmd measure_temp").readline()
        return float(temp.replace("temp=","").replace("'C\n",""))
    except Exception as e:
        return 0.0


class EquipmentMonitor:
    def __init__(self):
        self.config = Config()
        self.db_manager = DatabaseManager()
        self.camera_checker = CameraChecker()
        self.point_id = self.config.POINT_ID

        if not all([self.config.DB_HOST, self.config.DB_PORT, self.config.DB_NAME,
                    self.config.DB_USER, self.config.DB_PASSWORD]) or not self.point_id:
            raise ValueError("Не все переменные окружения загружены корректно")

    def format_status(self, device_type, device_name, is_online, value=None, current_dt=None):
        """Форматирование статуса для вывода с учетом переданного времени"""
        status = "✓ ON" if is_online else "✗ OFF"
        color_code = "92" if is_online else "91"
        
        if current_dt:
            timestamp = current_dt.strftime("%H:%M:%S")
        else:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        if value is not None:
            return f"\033[{color_code}m[{timestamp}] {device_type}: {status} ({value}°C)\033[0m"
        return f"\033[{color_code}m[{timestamp}] {device_type}: {status}\033[0m"

    def monitor_loop(self):
        """Основной цикл мониторинга"""
        print(f"Запуск мониторинга (ID: {self.point_id})...")
        print(f"Интервал проверки: {self.config.CHECK_INTERVAL} сек.")
        print("=" * 40)

        while True:
            try:
                # Получаем настройки точки
                time_s, time_do, gtm_offset = self.db_manager.get_point_info(self.point_id)

                # ИЗМЕНЕНИЕ: Возвращена оригинальная логика времени.
                # Берем просто текущее системное время сервера.
                now = datetime.now()
                actualization = now.replace(microsecond=0)
                current_hour = now.hour

                camera_status = {}

                # 1. Проверка IP камер
                ip_cameras = self.camera_checker.get_ip_cameras()
                for camera in ip_cameras:
                    status = self.camera_checker.check_ip_camera(camera)
                    camera_status[camera['name']] = 'ON' if status else 'OFF'
                    print(self.format_status(f"IP {camera['name']}", "", status, current_dt=now))

                # 2. Проверка USB камеры
                usb_status = self.camera_checker.check_usb_camera()
                camera_status['USB_Camera'] = 'ON' if usb_status else 'OFF'
                print(self.format_status("USB Camera", "", usb_status, current_dt=now))

                # 3. Проверка весов
                scales_status = self.camera_checker.check_scales()
                camera_status['Scales'] = 'ON' if scales_status else 'OFF'
                print(self.format_status("Scales", "", scales_status, current_dt=now))

                # 4. Проверка Микрофона
                mic_status = False
                if hasattr(self.camera_checker, 'check_microphone'):
                    mic_status = self.camera_checker.check_microphone()
                camera_status['Microphone'] = 'ON' if mic_status else 'OFF'
                print(self.format_status("Microphone", "", mic_status, current_dt=now))

                # 5. Проверка Динамика
                speaker_status = False
                if hasattr(self.camera_checker, 'check_speaker'):
                    speaker_status = self.camera_checker.check_speaker()
                camera_status['Speaker'] = 'ON' if speaker_status else 'OFF'
                print(self.format_status("Speaker", "", speaker_status, current_dt=now))

                # 6. Проверка температуры CPU
                cpu_temp = get_cpu_temp()
                camera_status['CPU_Temperature'] = cpu_temp
                print(self.format_status("CPU Temp", "", cpu_temp > 0, f"{cpu_temp:.1f}", current_dt=now))
                
                print('========================================')

                # Сохраняем в БД (теперь используется системное время в actualization)
                self.db_manager.save_equipment_status(
                    self.point_id, camera_status, time_s, time_do,
                    current_hour, actualization, cpu_temp
                )

            except Exception as e:
                print(f"\033[91mОшибка в цикле мониторинга: {e}\033[0m")
                time.sleep(5)

            time.sleep(self.config.CHECK_INTERVAL)


def main():
    monitor = EquipmentMonitor()
    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        print("\n\nМониторинг остановлен пользователем")
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")


if __name__ == "__main__":
    main()
