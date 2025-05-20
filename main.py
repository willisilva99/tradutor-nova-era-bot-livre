import os
import asyncio
import random
import discord
from discord.ext import commands, tasks

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
    "de olho nos hackers",
    "em lua de sangue",
]

# ───────────────────────────── status rotativo ─────────────────────────────
@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

# ───────────────────────────── evento on_ready ─────────────────────────────
@bot.event
async def on_ready():
    # evita rodar duas vezes se o gateway reconectar
    if getattr(bot, "ready_flag", False):
        return
    bot.ready_flag = True

    print(f"✅ Bot conectado como {bot.user}")

    # Sincroniza /comandos
    await bot.tree.sync()
    print("✅ Comandos de Slash sincronizados!")

    # Inicia o loop de status
    if not change_status.is_running():
        change_status.start()

    print("🚀 Bot está pronto para uso!")

# ───────────────────────────── carga de cogs ───────────────────────────────
async def load_cogs():
    cogs = [
        "cogs.admin",
        "cogs.utility",
        "cogs.global_ban",
        "cogs.ajuda_completa",
        "cogs.arcano",
        "cogs.nome",
        "cogs.temporario",
        "cogs.ranks",
        "cogs.recrutamento",
        # "cogs.sevendays",  # ← desativado, remove Telnet + ServerConfig
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"✅ Cog carregado: {cog}")
        except Exception as e:
            print(f"❌ Erro ao carregar {cog}: {e}")

# ───────────────────────────── main async ──────────────────────────────────
async def main():
    await load_cogs()
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não encontrada.")
        return
    await bot.start(TOKEN)

# ───────────────────────────── entrypoint ──────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
