import os
import asyncio
import random
import discord
from discord.ext import commands, tasks

# Importe seu DB e o dicionário/conexão do sevendays
from db import SessionLocal, ServerConfig
from cogs.sevendays import TelnetConnection, active_connections

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

STATUS_LIST = [
    "traduzindo",
    "matando zumbis",
    "falando com Willi",
    "nova era PvE"
]

@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

    # Define um status inicial
    activity = discord.Game(name="sesh.fyi | /help")
    await bot.change_presence(activity=activity)

    # Sincroniza comandos
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos de slash sincronizados!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

    if not change_status.is_running():
        change_status.start()

    # Restaura conexões do DB (opcional, mas recomendado)
    restore_telnet_connections()

    print("Bot está pronto!")

def restore_telnet_connections():
    """
    Lê todas as configs do DB e recria as conexões Telnet
    para cada guild com IP/porta/senha configurados.
    """
    with SessionLocal() as session:
        configs = session.query(ServerConfig).all()
        for cfg in configs:
            guild_id = cfg.guild_id
            # Se já houver, paramos e recriamos
            if guild_id in active_connections:
                active_connections[guild_id].stop()
                del active_connections[guild_id]

            ip = cfg.ip
            port = cfg.port
            password = cfg.password
            channel_id = cfg.channel_id

            # Cria a TelnetConnection
            conn = TelnetConnection(
                guild_id=guild_id,
                ip=ip,
                port=port,
                password=password,
                channel_id=channel_id,
                bot=bot
            )
            active_connections[guild_id] = conn
            conn.start()

    print("✅ Conexões Telnet restauradas a partir do DB.")

async def load_cogs():
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.utility")
    await bot.load_extension("cogs.sevendays")

async def main():
    await load_cogs()
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não encontrada.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
