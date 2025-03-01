import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///default.db")  # Variável de ambiente com fallback

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class ServerConfig(Base):
    __tablename__ = "server_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True, nullable=False)
    ip = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    password = Column(String(255), nullable=True)
    channel_id = Column(String(255), nullable=False)

class ServerStatusConfig(Base):
    __tablename__ = "server_status_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True, nullable=False)
    server_key = Column(String(255), nullable=False)
    channel_id = Column(String(255), nullable=False)
    message_id = Column(String(255), nullable=False)

Base.metadata.create_all(bind=engine)
