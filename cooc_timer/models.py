from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class TradePoint(Base):
    """Модель таблицы С1_Торговые_точки"""
    __tablename__ = 'С1_Торговые_точки'
    
    id_точки = Column(Integer, primary_key=True)
    GTM = Column(Integer) 

class ChefWork(Base):
    """Модель таблицы CV_работа_повара"""
    __tablename__ = 'CV_работа_повара'
    
    # УДАЛЕНО: id = Column(Integer, primary_key=True, autoincrement=True) 
    # В таблице БД нет столбца id. 
    # Для SQLAlchemy указываем составной первичный ключ из существующих полей:
    
    id_точки = Column(Integer, primary_key=True)
    Время_нач_работы = Column(DateTime, primary_key=True)
    
    Время_оконч_работы = Column(DateTime)
    Продолж_работы = Column(Integer)
