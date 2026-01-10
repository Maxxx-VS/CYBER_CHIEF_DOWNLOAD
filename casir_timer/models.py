from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class TradingPoint(Base):
    """
    Модель таблицы С1_Торговые_точки
    """
    __tablename__ = 'С1_Торговые_точки'
    
    id_точки = Column(Integer, primary_key=True)
    ВремяС = Column(String)
    ВремяДо = Column(String)
    GTM = Column(Integer)

class CashierWork(Base):
    """
    Модель таблицы CV_работа_кассира
    """
    __tablename__ = 'CV_работа_кассира'
    
    id_точки = Column(Integer, primary_key=True)
    Время_ухода_кассира = Column(DateTime, primary_key=True)
    Время_появления_кассира = Column(DateTime)
    Время_отсутствия_кассира = Column(Integer)
