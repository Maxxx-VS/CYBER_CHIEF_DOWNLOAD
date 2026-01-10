from sqlalchemy import Column, Integer, String, DateTime, Numeric
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class TradePoint(Base):
    __tablename__ = 'С1_Торговые_точки'
    
    id_точки = Column(Integer, primary_key=True)
    ВремяС = Column(String)
    ВремяДо = Column(String)
    GTM = Column(Integer)

class EquipmentMonitoring(Base):
    __tablename__ = 'CV_мониторинг_оборудования'
    
    id_точки = Column(Integer, primary_key=True)
    Камера_клиента = Column(String)
    Камера_повара = Column(String)
    Камера_кассира = Column(String)
    Камера_весов = Column(String)
    Подключение_весов = Column(String)
    Микрофон = Column(String)
    Динамик = Column(String)
    hour = Column(Integer)
    ВремяС = Column(String)
    ВремяДо = Column(String)
    Актуализация = Column(DateTime)
    Температура = Column(Numeric(3, 1))
