import os, re
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------
#  util
# ---------------------------------------------------
def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERRO: A variável de ambiente DATABASE_URL não está definida.")

engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------
#  modelos já existentes (mantive sem mudanças)
# ---------------------------------------------------
class ServerStatusConfig(Base):
    __tablename__ = "server_status_config"
    id          = Column(Integer, primary_key=True, index=True)
    guild_id    = Column(String, unique=True, index=True, nullable=False)
    server_key  = Column(String, nullable=False)
    channel_id  = Column(String, nullable=False)
    message_id  = Column(String, nullable=False)

class PlayerName(Base):
    __tablename__ = "player_name"
    id          = Column(Integer, primary_key=True, index=True)
    discord_id  = Column(String, unique=True, index=True, nullable=False)
    in_game_name= Column(String, nullable=False)

class GuildConfig(Base):
    __tablename__ = "guild_config"
    id                    = Column(Integer, primary_key=True, index=True)
    guild_id              = Column(String, unique=True, index=True, nullable=False)
    verification_channel_id = Column(String, nullable=True)
    log_channel_id          = Column(String, nullable=True)   # logs diversos
    staff_role_id           = Column(String, nullable=True)
    verificado_role_id      = Column(String, nullable=True)

# ---------------------------------------------------
#  Global Ban – histórico de bans
# ---------------------------------------------------
class GlobalBan(Base):
    __tablename__ = "global_bans"
    id          = Column(Integer, primary_key=True, index=True)
    discord_id  = Column(String, index=True, nullable=False)
    banned_by   = Column(String, nullable=False)
    reason      = Column(String, nullable=False)
    timestamp   = Column(DateTime, default=datetime.utcnow)

# ---------------------------------------------------
#  Global Ban – configuração de canal de log  (NOVA)
# ---------------------------------------------------
class GlobalBanLogConfig(Base):
    __tablename__ = "global_ban_log_config"
    id         = Column(Integer, primary_key=True, index=True)
    guild_id   = Column(String, unique=True, index=True, nullable=False)
    channel_id = Column(String, nullable=False)
    set_by     = Column(String, nullable=False)  # quem executou /gban setlog
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

# ---------------------------------------------------
#  criação de tabelas
# ---------------------------------------------------
try:
    Base.metadata.create_all(engine, checkfirst=True)
    print("✅ Banco de dados configurado corretamente.")
except Exception as e:
    print(f"❌ ERRO ao configurar o banco de dados: {e}")
