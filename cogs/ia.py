import discord
from discord.ext import commands
import os
import aiohttp
import json
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Carregar a chave da API do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
                # Fazer a requisição para a API Gemini
                response = await self.get_gemini_response(prompt)

                # Enviar a resposta no Discord
                await message.channel.send(f"**Resposta da IA:** {response}")
            except Exception as e:
                print(f"❌ Erro ao acessar a IA: {e}")  # Debug: mostrar erro
                await message.channel.send(f"❌ **Erro ao acessar a IA:** {e}")

    # Função para enviar a requisição para a API Gemini
    async def get_gemini_response(self, prompt: str) -> str:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEMINI_API_KEY}"
        }
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        # Realizando a requisição assíncrona
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=json.dumps(data)) as response:
                if response.status == 200:
                    result = await response.json()
                    # Verificar se o resultado está estruturado corretamente
                    try:
                        return result['choices'][0]['parts'][0]['text']
                    except KeyError:
                        raise Exception("Erro na estrutura da resposta da API Gemini.")
                else:
                    raise Exception(f"Erro ao acessar a Gemini API: {response.status}")

# Função para carregar o Cog
async def setup(bot):
    await bot.add_cog(IACog(bot))
