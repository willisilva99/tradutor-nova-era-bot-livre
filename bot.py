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
    
    # Define o status do bot como "Jogando sesh.fyi | /help"
    activity = discord.Game(name="sesh.fyi | /help")
    await bot.change_presence(activity=activity)

    # Sincroniza os slash commands
    try:
        synced = await bot.tree.sync()
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

# 🛠️ **Slash Command `/traduzir`**
@bot.tree.command(name="traduzir", description="Traduza uma mensagem pelo ID ou respondida")
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

# 🔥 **Slash Command `/ping` (Mostra Latência do Bot)**
@bot.tree.command(name="ping", description="Mostra o tempo de resposta do bot")
async def ping(interaction: discord.Interaction):
    """Mostra o ping do bot"""
    latency = round(bot.latency * 1000)  # Converte para ms
    await interaction.response.send_message(f"🏓 Pong! Latência: `{latency}ms`")

# 🧹 **Slash Command `/clear` (Apaga até 3000 mensagens)**
@bot.tree.command(name="clear", description="Limpa mensagens do chat (máx: 3000)")
@app_commands.describe(amount="Quantidade de mensagens a deletar (1-3000)")
async def clear(interaction: discord.Interaction, amount: int):
    """Apaga mensagens do canal"""
    if amount < 1 or amount > 3000:
        await interaction.response.send_message("⚠️ **Escolha um número entre 1 e 3000.**", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 **{len(deleted)} mensagens apagadas!**", ephemeral=True)

# 🔥 **Inicia o bot**
async def main():
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
