import os
import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
import random
from googletrans import Translator

# Cria o objeto de intents e o cliente (bot) sem prefixo, pois usaremos slash commands
intents = discord.Intents.all()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

translator = Translator()

# Lista de status para alternar periodicamente
STATUS_LIST = [
    "traduzindo",
    "mantando zumbi",
    "falando com willi",
    "nova era pve"
]

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    try:
        # Sincroniza os comandos de barra com o Discord
        synced = await tree.sync()
        print(f"Comandos de barra sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

    # Inicia a tarefa de mudança de status
    change_status.start()

@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

# Função de tradução usando googletrans
def translate_text(text: str, dest: str) -> str:
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro na tradução: {e}")
        return None

# Definindo um slash command para traduzir
# /traduzir texto: "Frase aqui" idioma: "pt/en/es"
@tree.command(name="traduzir", description="Traduza um texto para Português, Inglês ou Espanhol.")
@app_commands.describe(
    texto="O texto que você deseja traduzir",
    idioma="Idioma de destino (pt, en ou es)"
)
async def slash_traduzir(interaction: discord.Interaction, texto: str, idioma: str):
    # Verifica se o idioma está entre os suportados
    if idioma not in ["pt", "en", "es"]:
        await interaction.response.send_message(
            "Idiomas suportados: `pt` (Português), `en` (Inglês) ou `es` (Espanhol).",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)  # Mostra que o bot está "pensando"
    traducao = translate_text(texto, idioma)
    if not traducao:
        await interaction.followup.send("Houve um erro ao traduzir o texto. Tente novamente mais tarde.")
        return

    # Envia a resposta final
    await interaction.followup.send(f"**Tradução ({idioma}):** {traducao}")

# Função principal para rodar o bot
async def main():
    # Executa o bot usando a variável de ambiente TOKEN (Railway)
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
