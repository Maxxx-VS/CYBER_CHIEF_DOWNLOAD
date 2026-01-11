import paramiko
import os
import time
from config import SFTP_URL, SFTP_PORT, SFTP_USER, SFTP_PASSWORD, ID_POINT

class SFTPUploader:
    def __init__(self):
        # Логика обработки URL вида IP:PORT
        if SFTP_URL and ':' in SFTP_URL:
            self.host, port_str = SFTP_URL.split(':')
            self.port = int(port_str)
        else:
            self.host = SFTP_URL
            # Если порт не в URL, берем из переменной или дефолт 22
            self.port = int(SFTP_PORT) if SFTP_PORT else 22
            
        self.user = SFTP_USER
        self.password = SFTP_PASSWORD
        
        # Базовый путь на сервере (upload/violation/POINT_ID)
        self.remote_base = "upload/violation"
        self.target_dir = f"{self.remote_base}/{ID_POINT}"

    def _create_transport(self):
        """Создает и возвращает активное подключение"""
        try:
            transport = paramiko.Transport((self.host, self.port))
            transport.connect(username=self.user, password=self.password)
            return transport
        except Exception as e:
            print(f"SFTP Error: Не удалось подключиться к {self.host}:{self.port}. Ошибка: {e}")
            raise e

    def ensure_directories(self):
        """
        Проверяет наличие структуры директорий upload/violation/{ID_POINT}.
        Если директории нет - создает её.
        """
        transport = None
        sftp = None
        try:
            # print(f"SFTP: Проверка структуры директорий на сервере для точки {ID_POINT}...")
            transport = self._create_transport()
            sftp = paramiko.SFTPClient.from_transport(transport)

            # Последовательно проверяем/создаем вложенность
            paths_to_check = [
                "upload",
                "upload/violation",
                self.target_dir
            ]

            for path in paths_to_check:
                try:
                    sftp.stat(path)
                except FileNotFoundError:
                    # print(f"SFTP: Создание директории {path}...")
                    sftp.mkdir(path)
            
            return True

        except Exception as e:
            print(f"SFTP Critical Error при проверке директорий: {e}")
            return False
        finally:
            if sftp: sftp.close()
            if transport: transport.close()

    def upload_file(self, local_path, filename):
        """
        Загружает файл с локального диска (RAM) на SFTP и удаляет локальную копию.
        """
        transport = None
        sftp = None
        success = False
        
        # Проверка существования локального файла
        if not os.path.exists(local_path):
            print(f"SFTP Error: Локальный файл не найден: {local_path}")
            return False

        try:
            transport = self._create_transport()
            sftp = paramiko.SFTPClient.from_transport(transport)
            
            remote_path = f"{self.target_dir}/{filename}"
            # print(f"SFTP: Загрузка {filename} -> {remote_path}")
            
            sftp.put(local_path, remote_path)
            success = True
            # print(f"SFTP: Файл успешно загружен.")
            
        except Exception as e:
            print(f"SFTP Error при загрузке файла {filename}: {e}")
        finally:
            if sftp: sftp.close()
            if transport: transport.close()
            
            # ВАЖНО: Удаляем файл из RAM (ОЗУ) независимо от успеха загрузки
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError as e:
                    print(f"RAM Error: Не удалось удалить файл {local_path}: {e}")
        
        return success
