import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ✅ Garantir que a variável DATABASE_URL está definida (evita fallback para SQLite)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERRO: A variável de ambiente DATABASE_URL não está definida.")

# ✅ Criar conexão com o banco de dados
engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------
# Tabela ServerConfig
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
# Tabela ServerStatusConfig
# ---------------------------------------------------
class ServerStatusConfig(Base):
    __tablename__ = "server_status_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True, nullable=False)
    server_key = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    message_id = Column(String, nullable=False)


# ---------------------------------------------------
# Tabela GuildTicketConfig (Configurações de Ticket)
# ---------------------------------------------------
class GuildTicketConfig(Base):
    """
    Armazena as informações de ticket por guilda:
    - guild_id: ID da guilda do Discord
    - cargo_staff_id: ID do cargo Staff (permite acesso ao ticket)
    - channel_logs_id: ID do canal onde os logs de ticket serão enviados
    - channel_avaliation_id: ID do canal para avaliação (feedback)
    - category_ticket_id: ID da categoria onde os tickets serão criados
    """
    __tablename__ = "guild_ticket_config"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True, index=True, nullable=False)
    cargo_staff_id = Column(String, nullable=True)
    channel_logs_id = Column(String, nullable=True)
    channel_avaliation_id = Column(String, nullable=True)
    category_ticket_id = Column(String, nullable=True)


# ---------------------------------------------------
# Nova Tabela para Log de Mensagens de Tickets
# ---------------------------------------------------
class TicketMessage(Base):
    """
    Registra cada mensagem enviada em canais de ticket, permitindo histórico completo.
    - guild_id: guild em que o ticket está
    - channel_id: canal de texto do ticket
    - ticket_code: código único do ticket (ex: AB12XY)
    - author_id: ID de quem enviou a mensagem
    - content: texto da mensagem
    - timestamp: data/hora em que foi enviado
    """
    __tablename__ = "ticket_message"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    ticket_code = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------
# Funções de ajuda para TicketConfig
# ---------------------------------------------------
def get_or_create_guild_ticket_config(session, guild_id: str) -> GuildTicketConfig:
    """
    Busca a config de tickets pelo guild_id. Caso não exista, cria uma nova.
    """
    config = session.query(GuildTicketConfig).filter_by(guild_id=guild_id).first()
    if not config:
        config = GuildTicketConfig(guild_id=guild_id)
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


# ✅ Criar tabelas apenas se não existirem
try:
    Base.metadata.create_all(engine, checkfirst=True)
    print("✅ Banco de dados configurado corretamente.")
except Exception as e:
    print(f"❌ ERRO ao configurar o banco de dados: {e}")
