import discord
from discord.ext import commands
import openai
import os

# Carregar a chave da API do DeepSeek/OpenAI da variável de ambiente no Railway
openai.api_key = os.getenv("OPENAI_API_KEY")

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
            try:
                # Enviar a pergunta para a IA (usando OpenAI ou DeepSeek)
                response = openai.Completion.create(
                    engine="text-davinci-003",  # ou o modelo DeepSeek que você estiver usando
                    prompt=prompt,
                    max_tokens=150
                )
                answer = response.choices[0].text.strip()

                # Enviar resposta da IA no Discord
                await message.channel.send(f"**Resposta da IA:** {answer}")
            except Exception as e:
                # Se houver erro ao acessar a IA
                await message.channel.send(f"❌ **Erro ao acessar a IA:** {e}")

    # Config de carregamento do cog
async def setup(bot):
    await bot.add_cog(IACog(bot))
