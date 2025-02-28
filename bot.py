import os
import discord
from discord import app_commands
from discord.ext import tasks, commands
import asyncio
import random
from googletrans import Translator

intents = discord.Intents.all()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

translator = Translator()

STATUS_LIST = [
    "traduzindo",
    "mantando zumbi",
    "falando com willi",
    "nova era pve"
]

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

def translate_text(text: str, dest: str) -> str:
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro na tradução: {e}")
        return None

@tree.command(name="traduzir", description="Inicia o processo de tradução via reações de idioma.")
async def slash_traduzir(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Use este comando **respondendo** a uma mensagem que deseja traduzir, ou "
        "forneça o ID da mensagem com `$traduzir <ID>` no chat.\n\n"
        "**Vou enviar um prompt com bandeiras para escolher o idioma.**",
        ephemeral=True
    )

# Abaixo, o "bot_sub" é um Bot de comandos de texto
# que compartilha a conexão com o "bot" principal
discord_command_bot = commands.Bot(command_prefix="$", intents=intents)
discord_command_bot._connection = bot._connection
bot_sub = discord_command_bot

@bot_sub.command(name="traduzir")
async def traduzir(ctx, message_id: str = None):
    target_message = None

    if ctx.message.reference:
        try:
            target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            await ctx.send("Não foi possível recuperar a mensagem referenciada.")
            return
    elif message_id:
        try:
            target_message = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send("Não foi possível encontrar a mensagem com o ID fornecido.")
            return
    else:
        await ctx.send("Por favor, responda a mensagem que deseja traduzir ou forneça o ID da mensagem.")
        return

    prompt = await ctx.send(
        "Escolha o idioma para tradução:\n"
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
        await ctx.send("Tempo esgotado. Por favor, tente novamente.")
        return

    try:
        await prompt.delete()
    except Exception as e:
        print("Não foi possível apagar a mensagem de prompt:", e)

    if str(reaction.emoji) == "🇧🇷":
        target_language = "pt"
    elif str(reaction.emoji) == "🇺🇸":
        target_language = "en"
    elif str(reaction.emoji) == "🇪🇸":
        target_language = "es"
    else:
        target_language = "pt"

    msg = await ctx.send("Traduzindo...")

    try:
        translated_text = translate_text(target_message.content, target_language)
        if not translated_text:
            await msg.edit(content="Houve um erro ao tentar traduzir a mensagem.")
            return
        await msg.edit(content=f"**Tradução ({target_language}):** {translated_text}")
    except Exception as e:
        await msg.edit(content="Houve um erro ao tentar traduzir a mensagem. Tente novamente mais tarde.")
        print("Exceção durante tradução:", e)
        return

    feedback_emojis = ["👌", "👎"]
    for emoji in feedback_emojis:
        try:
            await msg.add_reaction(emoji)
        except Exception as e:
            print("Erro ao adicionar reação de feedback:", e)

    def feedback_check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in feedback_emojis and reaction.message.id == msg.id

    try:
        reaction_fb, _ = await bot.wait_for("reaction_add", timeout=30.0, check=feedback_check)
    except asyncio.TimeoutError:
        return

    if str(reaction_fb.emoji) == "👌":
        feedback = "\n\nFeedback: Joia, tradução aprovada!"
    elif str(reaction_fb.emoji) == "👎":
        feedback = "\n\nFeedback: Tradução não aprovada."
    else:
        feedback = ""
    try:
        await msg.edit(content=f"{msg.content}{feedback}")
    except Exception as e:
        print("Erro ao editar a mensagem com feedback:", e)

async def main():
    asyncio.create_task(bot.start(os.getenv("TOKEN")))
    await bot_sub.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
