from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import configparser

Base = declarative_base()


class Deletes(Base):
    __tablename__ = 'deletes'

    map_id = Column(Integer, primary_key=True)
    message = Column(BigInteger)
    channel = Column(BigInteger)
    time = Column(BigInteger)


class Autoclears(Base):
    __tablename__ = 'autoclears'

    id = Column(Integer, primary_key=True)
    channel = Column(BigInteger)
    user = Column(BigInteger)
    time = Column(Integer)


engine = create_engine('sqlite:///app.db')
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()
