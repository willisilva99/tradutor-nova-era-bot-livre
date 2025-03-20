import os
import asyncio
import random
import discord
from discord.ext import commands, tasks

# Importe seu DB e a conexão do sevendays
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
    if getattr(bot, "ready_flag", False):
        return  # Se já rodou uma vez, não executa novamente

    bot.ready_flag = True
    print(f"✅ Bot conectado como {bot.user}")

    # Sincroniza comandos de slash (necessário para que /ticketpanel etc. apareçam)
    await bot.tree.sync()
    print("✅ Comandos de Slash sincronizados!")

    if not change_status.is_running():
        change_status.start()

    restore_telnet_connections()
    print("Bot está pronto!")

def restore_telnet_connections():
    """Restaura conexões Telnet do banco de dados."""
    with SessionLocal() as session:
        configs = session.query(ServerConfig).all()
        for cfg in configs:
            try:
                guild_id = cfg.guild_id
                if guild_id in active_connections:
                    active_connections[guild_id].stop()
                    del active_connections[guild_id]

                conn = TelnetConnection(
                    guild_id=guild_id,
                    ip=cfg.ip,
                    port=cfg.port,
                    password=cfg.password,
                    channel_id=cfg.channel_id,
                    bot=bot
                )
                active_connections[guild_id] = conn
                conn.start()
            except Exception as e:
                print(f"❌ Erro ao restaurar Telnet para {guild_id}: {e}")
    print("✅ Conexões Telnet restauradas a partir do DB.")

async def load_cogs():
    # Inclua aqui o nome do seu novo cog "cogs.ajuda"
    cogs = [
        "cogs.admin",
        "cogs.utility",
        "cogs.sevendays",
        "cogs.serverstatus",
        "cogs.ajuda_completa"  # Novo cog de ajuda
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"✅ Cog carregado: {cog}")
        except Exception as e:
            print(f"❌ Erro ao carregar {cog}: {e}")

async def main():
    await load_cogs()
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não encontrada.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
