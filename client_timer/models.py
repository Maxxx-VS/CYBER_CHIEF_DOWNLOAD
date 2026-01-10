from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class TradingPoint(Base):
    __tablename__ = 'С1_Торговые_точки'
    
    id_точки = Column(Integer, primary_key=True)
    ВремяС = Column(String)  # В базе это строка "09:00"
    ВремяДо = Column(String)
    GTM = Column(Integer)

class CashierWork(Base):
    __tablename__ = 'CV_работа_кассира'
    
    id_точки = Column(Integer, primary_key=True)
    Время_ухода_кассира = Column(DateTime, primary_key=True)
    Время_появления_кассира = Column(DateTime)
    Время_отсутствия_кассира = Column(Integer)

class ClientPresence(Base):
    __tablename__ = 'CV_наличие_клиента'
    
    id_точки = Column(Integer, primary_key=True)
    Время_появления_клиента = Column(DateTime, primary_key=True)
    Время_ухода_клиента = Column(DateTime)
    Время_ожидания_клиента = Column(Integer)
