# models.py
from sqlalchemy import Column, Integer, DateTime, Numeric
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class RollCount(Base):
    # Указываем имя таблицы. Если оно изменится в БД, меняем только здесь.
    __tablename__ = 'CV_количество_ролов_2'

    point_id = Column('id_точки', Integer, primary_key=True)
    timestamp = Column('Дата_время_записи', DateTime, primary_key=True)
    hour = Column('Час_записи', Integer)
    count_weight = Column('Кол-во_по_весам', Integer)
    count_detection = Column('Кол-во_по_детекции', Integer)
    max_count_weight = Column('Макс-кол-во_по_весам', Integer)
    max_count_detection = Column('Макс-кол-во_по_детекции', Integer)
    mass = Column('Масса', Numeric(10, 3))
