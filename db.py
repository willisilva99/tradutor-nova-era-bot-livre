import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")  # Variável de ambiente no Railway

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class ServerConfig(Base):
    __tablename__ = "server_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True)
    ip = Column(String)
    port = Column(Integer)
    password = Column(String)
    channel_id = Column(String)

class ServerStatusConfig(Base):
    __tablename__ = "server_status_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True)
    server_key = Column(String)
    channel_id = Column(String)
    message_id = Column(String)

Base.metadata.create_all(bind=engine)
