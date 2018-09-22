from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
import configparser


url = 'sqlite:///app.db'

c = configparser.SafeConfigParser()
c.read('config.ini')
dest_url = c.get('DEFAULT', 'sql')
print(dest_url)

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


engine = create_engine(url)
Base.metadata.create_all(bind=engine)

engine2 = create_engine(dest_url)
Base.metadata.create_all(bind=engine2)

Session = sessionmaker(bind=engine)
session = Session()

Session2 = sessionmaker(bind=engine2)
session_dest = Session2()


for x in session.query(Deletes):
    session_dest.merge(x)

for x in session.query(Autoclears):
    session_dest.merge(x)

session_dest.commit()
