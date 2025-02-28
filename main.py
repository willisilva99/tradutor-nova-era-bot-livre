import os
import asyncio
import random
import discord
from discord.ext import commands, tasks

# Carrega o token do bot via variável de ambiente
TOKEN = os.getenv("TOKEN")

# Se quiser, pode mudar Intents conforme a necessidade
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Cria a instância do bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Lista de status aleatórios
STATUS_LIST = [
    "traduzindo",
    "matando zumbis",
    "falando com Willi",
    "nova era PvE"
]

@tasks.loop(minutes=5)
async def change_status():
    """Muda o status do bot periodicamente."""
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

@bot.event
async def on_ready():
    """É chamado quando o bot fica online e pronto para uso."""
    print(f"✅ Bot conectado como {bot.user}")

    # Define um status inicial
    activity = discord.Game(name="sesh.fyi | /help")
    await bot.change_presence(activity=activity)

    # Tenta sincronizar comandos de slash (globais ou guild)
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos de slash sincronizados!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

    # Inicia a task de mudança de status, se não estiver rodando
    if not change_status.is_running():
        change_status.start()

async def load_cogs():
    """
    Carrega as extensões (cogs) localizadas na pasta cogs.
    Adicione mais cogs conforme necessidade.
    """
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.utility")

async def main():
    # Carrega as cogs
    await load_cogs()

    # Inicia o bot
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não encontrada.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
