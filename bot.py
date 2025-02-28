import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
from googletrans import Translator

# Configurações do bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

# Slash Commands
tree = app_commands.CommandTree(bot)

# Tradutor
translator = Translator()

# Lista de status aleatórios
STATUS_LIST = [
    "traduzindo",
    "mantando zumbi",
    "falando com willi",
    "nova era pve"
]

# 🔄 Muda o status do bot periodicamente
@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Comandos de barra sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")
    change_status.start()

# 🔄 Função de tradução usando googletrans
def translate_text(text: str, dest: str) -> str:
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro na tradução: {e}")
        return None

# 🛠️ **Slash Command** `/traduzir`
@tree.command(name="traduzir", description="Traduza uma mensagem pelo ID ou respondida")
@app_commands.describe(
    message_id="ID da mensagem (opcional). Se não informar, responda a uma mensagem."
)
async def slash_traduzir(interaction: discord.Interaction, message_id: str = None):
    """Slash command que traduz um texto baseado em um ID de mensagem ou reply"""
    await interaction.response.defer(thinking=True)
    channel = interaction.channel
    target_message = None

    if message_id:
        try:
            target_message = await channel.fetch_message(message_id)
        except:
            await interaction.followup.send("❌ **Mensagem não encontrada!** Verifique o ID.")
            return
    else:
        ref = interaction.message.reference
        if ref:
            try:
                target_message = await channel.fetch_message(ref.message_id)
            except:
                pass

        if not target_message:
            await interaction.followup.send("⚠️ **Forneça um ID ou responda a uma mensagem!**")
            return

    # 🔹 Envia mensagem com as bandeiras para escolher idioma
    prompt = await channel.send(
        "🌎 **Escolha o idioma para tradução:**\n"
        "🇧🇷 - Português\n"
        "🇺🇸 - Inglês\n"
        "🇪🇸 - Espanhol"
    )
    emojis = ["🇧🇷", "🇺🇸", "🇪🇸"]
    for emoji in emojis:
        await prompt.add_reaction(emoji)

    def check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in emojis and reaction.message.id == prompt.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send("⏳ **Tempo esgotado! Tente novamente.**")
        return

    try:
        await prompt.delete()
    except:
        pass

    # 🔄 Mapeia a bandeira para o idioma
    target_language = {"🇧🇷": "pt", "🇺🇸": "en", "🇪🇸": "es"}.get(str(reaction.emoji), "pt")

    msg = await channel.send("🔄 **Traduzindo...**")

    try:
        translated_text = translate_text(target_message.content, target_language)
        if not translated_text:
            await msg.edit(content="❌ **Erro na tradução!**")
            return
        await msg.edit(content=f"✅ **Tradução ({target_language}):** {translated_text}")
    except Exception as e:
        await msg.edit(content="❌ **Erro ao traduzir a mensagem!**")
        print("Erro:", e)
        return

    # 👍👎 Adiciona reações de feedback
    feedback_emojis = ["👌", "👎"]
    for emoji in feedback_emojis:
        await msg.add_reaction(emoji)

# 💬 **Comando de Texto** `$traduzir`
@bot.command(name="traduzir")
async def traduzir(ctx, message_id: str = None):
    """Comando que traduz uma mensagem via reação"""
    target_message = None

    if ctx.message.reference:
        try:
            target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except:
            await ctx.send("❌ **Erro ao encontrar a mensagem respondida.**")
            return
    elif message_id:
        try:
            target_message = await ctx.channel.fetch_message(message_id)
        except:
            await ctx.send("❌ **ID inválido!**")
            return
    else:
        await ctx.send("⚠️ **Responda a uma mensagem ou forneça um ID!**")
        return

    prompt = await ctx.send(
        "🌎 **Escolha o idioma para tradução:**\n"
        "🇧🇷 - Português\n"
        "🇺🇸 - Inglês\n"
        "🇪🇸 - Espanhol"
    )
    emojis = ["🇧🇷", "🇺🇸", "🇪🇸"]
    for emoji in emojis:
        await prompt.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in emojis and reaction.message.id == prompt.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("⏳ **Tempo esgotado! Tente novamente.**")
        return

    try:
        await prompt.delete()
    except:
        pass

    target_language = {"🇧🇷": "pt", "🇺🇸": "en", "🇪🇸": "es"}.get(str(reaction.emoji), "pt")

    msg = await ctx.send("🔄 **Traduzindo...**")

    try:
        translated_text = translate_text(target_message.content, target_language)
        if not translated_text:
            await msg.edit(content="❌ **Erro na tradução!**")
            return
        await msg.edit(content=f"✅ **Tradução ({target_language}):** {translated_text}")
    except:
        await msg.edit(content="❌ **Erro ao traduzir!**")
        return

    # 👍👎 Adiciona feedback
    for emoji in ["👌", "👎"]:
        await msg.add_reaction(emoji)

# 🔥 **Inicia o bot**
async def main():
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
