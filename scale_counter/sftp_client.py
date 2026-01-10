# sftp_client.py
import paramiko
import os
import posixpath

class SFTPHandler:
    def __init__(self, config):
        self.host = config.SFTP_HOST
        self.port = config.SFTP_PORT
        self.user = config.SFTP_USER
        self.password = config.SFTP_PASSWORD
        self.transport = None
        self.sftp = None
        
    def connect(self):
        try:
            self.transport = paramiko.Transport((self.host, self.port))
            self.transport.connect(username=self.user, password=self.password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            print(f"SFTP Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"SFTP Connection failed: {e}")
            return False

    def ensure_remote_directories(self, remote_paths):
        """Рекурсивно проверяет и создает директории на сервере"""
        if not self.sftp:
            if not self.connect():
                return

        for path in remote_paths:
            self._makedirs(path)

    def _makedirs(self, path):
        """Аналог os.makedirs для SFTP"""
        dirs = path.split('/')
        current_path = ""
        for d in dirs:
            if not d: continue
            current_path = posixpath.join(current_path, d)
            try:
                self.sftp.stat(current_path)
            except IOError:
                try:
                    self.sftp.mkdir(current_path)
                    print(f"Created remote dir: {current_path}")
                except Exception as e:
                    print(f"Error creating dir {current_path}: {e}")

    def upload_file(self, local_path, remote_path):
        if not self.sftp:
            self.connect()
        
        try:
            remote_path = remote_path.replace('\\', '/')
            self.sftp.put(local_path, remote_path)
            return True
        except Exception as e:
            print(f"Failed to upload {local_path} to {remote_path}: {e}")
            try:
                self.connect()
                self.sftp.put(local_path, remote_path)
                return True
            except:
                return False

    def close(self):
        if self.sftp: self.sftp.close()
        if self.transport: self.transport.close()
