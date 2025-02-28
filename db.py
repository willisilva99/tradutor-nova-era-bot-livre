# db.py
import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

# Lê a URL do PostgreSQL do Railway
DATABASE_URL = os.getenv("DATABASE_URL")  # Ex: 'postgresql://user:pass@host:port/dbname'

# Cria a engine do SQLAlchemy
engine = create_engine(DATABASE_URL, echo=False)

# Sessão
SessionLocal = sessionmaker(bind=engine)

# Base para modelos
Base = declarative_base()

# Exemplo de modelo
class ServerConfig(Base):
    __tablename__ = "server_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True)
    ip = Column(String)
    port = Column(Integer)
    password = Column(String)
    channel_id = Column(String, nullable=True)

# Cria as tabelas (se não existir)
Base.metadata.create_all(bind=engine)
