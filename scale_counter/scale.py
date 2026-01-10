# scale.py
import serial
import time
import glob

class ScaleReader:
    def __init__(self, config):
        self.config = config
        self.port = config.SCALE_PORT
        self.baudrate = config.SCALE_BAUDRATE
        self.ser = None
        self.last_stable_weight = 0
        # Удалены неиспользуемые переменные self.current_weight и self.current_status
        
        self._find_scale()
        
    def _find_scale(self):
        try:
            # Ищем USB-serial устройства
            usb_devices = glob.glob('/dev/ttyUSB*')
            
            if not usb_devices:
                return
                
            for device in usb_devices:
                if self._test_scale_device(device):
                    self.port = device
                    return
            
        except Exception as e:
            pass
    
    def _test_scale_device(self, device_path):
        """Проверка, отвечает ли устройство по протоколу весов"""
        try:
            test_ser = serial.Serial(
                port=device_path,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            # Посылаем запрос ENQ (0x05)
            test_ser.write(b'\x05')
            time.sleep(0.2)
            
            # Ждем ответ ACK (0x06)
            if test_ser.in_waiting > 0 and test_ser.read(1) == b'\x06':
                test_ser.close()
                return True
                
            test_ser.close()
            return False
            
        except Exception:
            return False
    
    def connect(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            time.sleep(3) # Ожидание инициализации порта
            return True
        except Exception as e:
            return False
    
    def read_weight(self):
        if not self.ser:
            return None
            
        try:
            # 1. Запрос веса (ENQ)
            self.ser.write(b'\x05')
            time.sleep(0.2)
            
            # 2. Если получили ACK (0x06)
            if self.ser.in_waiting > 0 and self.ser.read(1) == b'\x06':
                # 3. Запрашиваем передачу данных (DC1)
                self.ser.write(b'\x11')
                time.sleep(0.5)
                
                packet_start = False
                
                # Поиск начала пакета (SOH + STX -> 0x01, 0x02)
                while self.ser.in_waiting > 0:
                    byte = self.ser.read(1)
                    if byte == b'\x01':
                        next_byte = self.ser.read(1)
                        if next_byte == b'\x02':
                            packet_start = True
                            break
                
                if packet_start:
                    data = b''
                    # Читаем до конца пакета (ETX -> 0x03)
                    while True:
                        if self.ser.in_waiting > 0:
                            byte = self.ser.read(1)
                            if byte == b'\x03':
                                break
                            data += byte
                    
                    # Пропускаем проверочный байт, если он есть
                    if self.ser.in_waiting > 0:
                        self.ser.read(1)
                    
                    # Парсинг данных
                    if len(data) >= 11:
                        data_str = data.decode('ascii', errors='ignore')
                        
                        status = data_str[0]       # S - стабильно, U - нестабильно
                        sign = data_str[1]         # -, +, F (перегруз)
                        weight_str = data_str[2:8] # Значение веса
                        units = data_str[8:10]     # Единицы измерения
                        
                        try:
                            weight_clean = weight_str.strip()
                            weight_kg = float(weight_clean)
                            weight_grams = weight_kg * 1000
                            
                            # Логика определения изменения веса
                            weight_change = 0
                            is_exceeded = False

                            if status == 'S':
                                weight_change = abs(weight_grams - self.last_stable_weight)
                                is_exceeded = weight_change >= self.config.WEIGHT_THRESHOLD

                            return {
                                'status': status,
                                'sign': sign,
                                'weight_kg': weight_kg,
                                'weight_grams': weight_grams,
                                'units': units,
                                'weight_change': weight_change,
                                'is_threshold_exceeded': is_exceeded
                            }
                                
                        except ValueError:
                            pass
                        
        except Exception:
            pass
            
        return None

    def update_stable_weight(self, new_weight):
        self.last_stable_weight = new_weight

    def format_output(self, data):
        if not data:
            return "Нет данных"
    
        output = "Вес: "
    
        if data['sign'] == '-':
            output += "-"
        elif data['sign'] == 'F':
            output += "ПЕРЕГРУЗКА "
    
        # Форматируем вес с тремя знаками после запятой (0.000 кг)
        output += f"{data['weight_kg']:.3f} kg"
    
        # Выводим изменение веса с одним знаком после запятой (X.Xг)
        output += f" | Изменение: {data['weight_change']:.1f}г"
    
        return output

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
