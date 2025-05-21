import os
import asyncio
import random

import discord
from discord.ext import commands, tasks

TOKEN = os.getenv("TOKEN")

# ─────────────────────────── Intents ────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.members = True     # <<< ESSENCIAL para varrer guild.members / fetch_members
intents.presences = False  # não precisa de presences, a menos que queira status dos users

# ───────────────────────── Bot Client ──────────────────────────
bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────── Status Loop ────────────────────────
STATUS_LIST = [
    "traduzindo",
    "matando zumbis",
    "falando com Willi",
    "de olho nos hackers",
    "em lua de sangue",
]

@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

# ─────────────────────────── on_ready ───────────────────────────
@bot.event
async def on_ready():
    if getattr(bot, "ready_flag", False):
        return
    bot.ready_flag = True

    print(f"✅ Bot conectado como {bot.user}")

    # Sincroniza os comandos de slash
    await bot.tree.sync()
    print("✅ Comandos de Slash sincronizados!")

    # Inicia o loop de status
    if not change_status.is_running():
        change_status.start()

    print("🚀 Bot está pronto para uso!")

# ─────────────────────────── Load Cogs ──────────────────────────
async def load_cogs():
    cogs = [
        "cogs.admin",
        "cogs.utility",
        "cogs.global_ban",      # <-- Cog de ban global com recheck a cada 5 min
        "cogs.ajuda_completa",
        "cogs.arcano",
        "cogs.nome",
        "cogs.temporario",
        "cogs.ranks",
        "cogs.recrutamento",
        "cogs.serverstatus", 
        "cogs.profanity", 
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"✅ Cog carregado: {cog}")
        except Exception as e:
            print(f"❌ Erro ao carregar {cog}: {e}")

# ───────────────────────────── Main ─────────────────────────────
async def main():
    await load_cogs()
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não encontrada.")
        return
    await bot.start(TOKEN)

# ────────────────────────── Entrypoint ──────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
