import discord
from discord.ext import commands
import os
import aiohttp
import json

# Carregar a chave da API DeepSeek
DEEPSEEK_API_KEY = os.getenv("OPENAI_API_KEY")

# Configurações do bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

class IACog(commands.Cog):
    """Cog para respostas automáticas da IA quando a pergunta começar com '?'."""

    def __init__(self, bot):
        self.bot = bot

    # Evento que escuta todas as mensagens
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar mensagens enviadas pelo próprio bot
        if message.author == self.bot.user:
            return

        # Verificar se a mensagem começa com '?', indicando uma pergunta
        if message.content.startswith("?"):
            prompt = message.content[1:].strip()  # Remover o '?' e espaços extras
            print(f"📩 Pergunta recebida: {prompt}")  # Debug: mostrar a pergunta

            try:
                # Fazer a requisição para a API DeepSeek
                response = await self.get_deepseek_response(prompt)

                # Enviar a resposta no Discord
                await message.channel.send(f"**Resposta da IA:** {response}")
            except Exception as e:
                print(f"❌ Erro ao acessar a IA: {e}")  # Debug: mostrar erro
                await message.channel.send(f"❌ **Erro ao acessar a IA:** {e}")

        # Certifique-se de que os comandos do bot ainda sejam processados
        await self.bot.process_commands(message)

    # Função para enviar a requisição para a API DeepSeek
    async def get_deepseek_response(self, prompt: str) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Você é um assistente útil."},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }

        # Realizando a requisição assíncrona
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=json.dumps(data)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']
                else:
                    raise Exception(f"Erro ao acessar a DeepSeek API: {response.status}")

# Config de carregamento do cog
@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user.name}")

@bot.event
async def on_disconnect():
    print("Bot desconectado.")

# Carregar os cogs
async def setup(bot):
    await bot.add_cog(IACog(bot))

# Iniciar o bot
bot.run(os.getenv("DISCORD_TOKEN"))
