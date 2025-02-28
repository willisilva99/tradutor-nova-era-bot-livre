import os
import discord
from discord.ext import commands, tasks
import requests
import asyncio
import random

# Cria o bot com o prefixo "$" e com todos os intents necessários
bot = commands.Bot(command_prefix="$", intents=discord.Intents.all())

# Lista de status que o bot exibirá
STATUS_LIST = [
    "traduzindo",
    "mantando zumbi",
    "falando com willi",
    "nova era pve"
]

# Função para traduzir o texto utilizando a API do LibreTranslate
def translate_text(text, target_language):
    url = "https://libretranslate.com/translate"
    payload = {
        "q": text,
        "source": "auto",   # Detecta automaticamente o idioma da mensagem
        "target": target_language,
        "format": "text"
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["translatedText"]

# Evento on_ready: quando o bot estiver online
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')
    # Inicia a tarefa que altera o status periodicamente
    change_status.start()

# Tarefa que alterna o status do bot a cada 5 minutos (ajuste o intervalo conforme desejar)
@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

# Comando $traduzir
@bot.command(name="traduzir")
async def traduzir(ctx, message_id: str = None):
    target_message = None

    # Se o comando for usado como resposta a uma mensagem
    if ctx.message.reference:
        try:
            target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            await ctx.send("Não foi possível recuperar a mensagem referenciada.")
            return
    # Se o usuário fornecer um ID de mensagem
    elif message_id:
        try:
            target_message = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send("Não foi possível encontrar a mensagem com o ID fornecido.")
            return
    else:
        await ctx.send("Por favor, responda a mensagem que deseja traduzir ou forneça o ID da mensagem.")
        return

    # Envia uma mensagem com as opções de idioma (bandeiras)
    prompt = await ctx.send(
        "Escolha o idioma para tradução:\n"
        "🇧🇷 - Português\n"
        "🇺🇸 - Inglês\n"
        "🇪🇸 - Espanhol"
    )
    emojis = ["🇧🇷", "🇺🇸", "🇪🇸"]
    for emoji in emojis:
        await prompt.add_reaction(emoji)

    # Define o filtro para aceitar apenas a reação do autor do comando
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in emojis and reaction.message.id == prompt.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except Exception:
        await ctx.send("Tempo esgotado. Por favor, tente novamente.")
        return

    # Mapeia a reação escolhida para o código do idioma
    if str(reaction.emoji) == "🇧🇷":
        target_language = "pt"
    elif str(reaction.emoji) == "🇺🇸":
        target_language = "en"
    elif str(reaction.emoji) == "🇪🇸":
        target_language = "es"
    else:
        target_language = "pt"

    await ctx.send("Traduzindo...")

    try:
        translated_text = translate_text(target_message.content, target_language)
        await ctx.send(f"**Tradução ({target_language}):** {translated_text}")
    except Exception as e:
        await ctx.send("Houve um erro ao tentar traduzir a mensagem. Tente novamente mais tarde.")
        print(e)

# Função principal para iniciar o bot usando a variável de ambiente do Railway
async def main():
    async with bot:
        await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
