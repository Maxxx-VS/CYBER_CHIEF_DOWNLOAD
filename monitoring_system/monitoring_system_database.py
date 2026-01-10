from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from monitoring_system_config import Config
from monitoring_system_models import Base, TradePoint, EquipmentMonitoring

class DatabaseManager:
    def __init__(self):
        # ИЗМЕНЕНИЕ: Добавлены параметры для авто-реконнекта (pool_pre_ping=True)
        self.engine = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
        )
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()
    
    def get_point_info(self, point_id):
        """
        Получает время работы и часовой пояс (GTM) точки.
        Возвращает: (time_s, time_do, gtm_offset)
        """
        session = self.get_session()
        try:
            point = session.query(TradePoint).filter(TradePoint.id_точки == point_id).first()
            
            if point:
                time_s = point.ВремяС
                time_do = point.ВремяДо
                gtm_offset = point.GTM if point.GTM is not None else 3 
                
                if hasattr(time_s, 'strftime'):
                    time_s = time_s.strftime('%H:%M')
                if hasattr(time_do, 'strftime'):
                    time_do = time_do.strftime('%H:%M')
                    
                return time_s, time_do, gtm_offset
            else:
                return "09:00", "23:15", 3
                
        except Exception:
            return "09:00", "23:15", 3
        finally:
            session.close()
    
    def save_equipment_status(self, point_id, camera_status, time_s, time_do, current_hour, actualization, temperature):
        session = self.get_session()
        try:
            record = session.query(EquipmentMonitoring).filter(EquipmentMonitoring.id_точки == point_id).first()
            
            if not record:
                record = EquipmentMonitoring(id_точки=point_id)
                session.add(record)
            
            record.Камера_клиента = camera_status.get('CLIENT', 'OFF')
            record.Камера_повара = camera_status.get('COOK', 'OFF')
            record.Камера_кассира = camera_status.get('CASSIR', 'OFF')
            record.Камера_весов = camera_status.get('USB_Camera', 'OFF')
            record.Подключение_весов = camera_status.get('Scales', 'OFF')
            record.Микрофон = camera_status.get('Microphone', 'OFF')
            record.Динамик = camera_status.get('Speaker', 'OFF')
            
            record.hour = current_hour
            record.ВремяС = time_s
            record.ВремяДо = time_do
            record.Актуализация = actualization
            record.Температура = float(temperature)
            
            session.commit()
            
        except Exception as e:
            print(f"\033[91mОшибка БД: {e}\033[0m")
            session.rollback()
        finally:
            session.close()
