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
            print(f"📩 Pergunta recebida: {prompt}")  # Debug: mostrar a pergunta

            try:
                # Enviar a pergunta para a IA (usando OpenAI ou DeepSeek)
                print("🔄 Enviando requisição para a API...")  # Debug: indicar que a requisição foi feita
                
                # Nova interface da API com chat
                response = openai.chat.Completion.create(
                    model="gpt-3.5-turbo",  # ou gpt-4 se você tiver acesso
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                # Imprimir a resposta completa para debug
                print(f"🌐 Resposta da IA: {response}")  # Debug: mostrar a resposta completa da API

                answer = response['choices'][0]['message']['content'].strip()

                # Enviar resposta da IA no Discord
                await message.channel.send(f"**Resposta da IA:** {answer}")
            except Exception as e:
                # Se houver erro ao acessar a IA
                print(f"❌ Erro ao acessar a IA: {e}")  # Debug: mostrar erro
                await message.channel.send(f"❌ **Erro ao acessar a IA:** {e}")

        # Certifique-se de que os comandos do bot ainda sejam processados
        await self.bot.process_commands(message)

# Config de carregamento do cog
async def setup(bot):
    await bot.add_cog(IACog(bot))
