import os
from datetime import datetime
import re
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Index
from sqlalchemy.orm import declarative_base, sessionmaker

# Função para normalizar perguntas (cache de IA)
def normalize(text: str) -> str:
    """
    Normaliza o texto: sem acentos, sem pontuação, minúsculo e espaços únicos.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text)

# Verifica se a variável de ambiente DATABASE_URL está definida
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERRO: A variável de ambiente DATABASE_URL não está definida.")

# Cria a engine de conexão
engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

# Sessão para interagir com o banco
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa
Base = declarative_base()

# ---------------------------------------------------
# Tabela ServerConfig (já existente)
# ---------------------------------------------------
class ServerConfig(Base):
    __tablename__ = "server_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True, nullable=False)
    ip = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    password = Column(String, nullable=True)
    channel_id = Column(String, nullable=False)

# ---------------------------------------------------
# Tabela ServerStatusConfig (já existente)
# ---------------------------------------------------
class ServerStatusConfig(Base):
    __tablename__ = "server_status_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True, nullable=False)
    server_key = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    message_id = Column(String, nullable=False)

# ---------------------------------------------------
# Tabela PlayerName (já existente)
# ---------------------------------------------------
class PlayerName(Base):
    __tablename__ = "player_name"

    id = Column(Integer, primary_key=True, index=True)
    discord_id = Column(String, unique=True, index=True, nullable=False)
    in_game_name = Column(String, nullable=False)

# ---------------------------------------------------
# Tabela GuildConfig (NOVA) - para verificação/etc.
# ---------------------------------------------------
class GuildConfig(Base):
    __tablename__ = "guild_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True, nullable=False)
    verification_channel_id = Column(String, nullable=True)
    log_channel_id          = Column(String, nullable=True)
    staff_role_id           = Column(String, nullable=True)
    verificado_role_id      = Column(String, nullable=True)
    # Se quiser mais campos (wait_time, etc.), adicione aqui.

# ---------------------------------------------------
# Tabela AI Cache (nova) para memórias da IA
# ---------------------------------------------------
class AICache(Base):
    __tablename__ = "ai_cache"
    __table_args__ = (Index("ix_ai_cache_question", "question"),)

    id         = Column(Integer, primary_key=True)
    question   = Column(Text, unique=True, nullable=False, index=True)
    answer     = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

# Cria as tabelas se não existirem
try:
    Base.metadata.create_all(engine, checkfirst=True)
    print("✅ Banco de dados configurado corretamente.")
except Exception as e:
    print(f"❌ ERRO ao configurar o banco de dados: {e}")
