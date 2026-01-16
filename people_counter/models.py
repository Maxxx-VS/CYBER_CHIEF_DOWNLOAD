from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from datetime import datetime

# Создаем базовый класс для моделей
Base = declarative_base()

class TradingPoint(Base):
    """
    Модель таблицы С1_Торговые_точки
    """
    __tablename__ = 'С1_Торговые_точки'
    
    id_точки = Column(Integer, primary_key=True)
    ВремяС = Column(Text)  # Формат "HH:MM"
    ВремяДо = Column(Text)  # Формат "HH:MM" 
    GTM = Column(Integer)  # Смещение времени
    
    def __repr__(self):
        return f"<TradingPoint(id_точки={self.id_точки}, время_с={self.ВремяС}, время_до={self.ВремяДо}, gtm={self.GTM})>"

class PeopleCounter(Base):
    """
    Модель таблицы CV_счетчик_людей
    """
    __tablename__ = 'CV_счетчик_людей'
    
    id_точки = Column(Integer, primary_key=True)
    Дата_время_записи = Column(DateTime, primary_key=True)
    Дата_записи = Column(Date)
    Час_записи = Column(Integer)
    Количество_людей = Column(Integer)
    
    def __repr__(self):
        return f"<PeopleCounter(id_точки={self.id_точки}, дата_время={self.Дата_время_записи}, количество={self.Количество_людей})>"

# Функции для работы с базой данных
def get_db_session():
    """Создает и возвращает сессию базы данных"""
    connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    Session = sessionmaker(bind=engine)
    return Session()

def init_db():
    """Инициализация базы данных (создание таблиц если их нет)"""
    connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    Base.metadata.create_all(engine)
