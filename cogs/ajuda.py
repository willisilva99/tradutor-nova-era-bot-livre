import discord
from discord.ext import commands

# Palavras-chave que disparam a resposta
KEYWORDS = [
    "comandos do servidor",
    "qual comando",
    "como ganha drop",
    "comandos"
]

# Texto (ou embed) com os comandos de barra
SLASH_COMMANDS_INFO = (
    "**Comandos com Barra (/)**\n"
    "`/credito` - Concede 50 créditos por hora.\n"
    "`/vip` - Concede 100 créditos por hora.\n"
    "`/bonus` - Concede 500 créditos por hora.\n"
    "`/vote` - Ao votar no site, você ganha moeda VIP e zombite.\n"
    "`/lua` - Teleporta você para a lua comunitária.\n"
    "`/market` - Leva você até o market, onde ficam todas as máquinas.\n"
    "`/safe` - Vai até o market, fica 60s e retorna para onde você digitou o comando.\n"
    "`/airdrop` - Ganha um drop.\n"
    "`/ping` - Mostra seu ping.\n"
    "`/who` - Exibe sua localização, total de jogadores online e próximos.\n"
    "`/wallet` - Mostra seu saldo de crédito na carteira.\n"
    "`/settele [nome]` - Cria um teleporte com o nome informado.\n"
    "`/renametele [nome]` - Renomeia um teleporte existente.\n"
    "`/telelist` - Lista todos os seus teleportes.\n"
    "`/removetele [nome]` - Apaga o teleporte com o nome especificado.\n"
    "`/tele [nome]` - Teleporta para o teleporte criado com o nome informado.\n"
    "`/arena` - Teleporta você até a arena PvP.\n"
    "`/drone` - Exibe localização do drone perdido.\n"
    "`/reset` - Reseta seu personagem (apaga tudo e começa do zero).\n"
    "`/claim` - Resgata itens do site que você comprou."
)

# Texto (ou embed) com os comandos de exclamação
EXCLAMATION_COMMANDS_INFO = (
    "**Comandos com Exclamação (!)**\n"
    "`!vote` - Abre o site de votação.\n"
    "`!amigo [nome]` - Teleporta você até o amigo especificado.\n"
    "`!discord` - Entra no Discord do servidor.\n"
    "`!loteria` - Exibe informações da loteria de dukes.\n"
    "`!loteria entrar` - Entra na loteria com 1000 dukes.\n"
    "`!loc` - Exibe sua localização.\n"
    "`!fps` - Mostra seu FPS.\n"
    "`!bug` - Usa para se livrar de bugs que te prendam.\n"
    "`!killme` - Mata seu personagem.\n"
    "`!suicide` - Executa o comando para suicídio do personagem."
)


class AjudaComandosCog(commands.Cog):
    """Envia a lista de comandos se detectar palavras-chave na mensagem."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bots (inclusive do próprio bot)
        if message.author.bot:
            return
        
        # Transforma a mensagem em minúsculas para comparação
        content_lower = message.content.lower()
        
        # Verifica se a mensagem contém alguma das palavras-chave
        if any(keyword in content_lower for keyword in KEYWORDS):
            # Exemplo de uso de embed
            embed = discord.Embed(
                title="Lista de Comandos do Servidor",
                description=(
                    f"{SLASH_COMMANDS_INFO}\n\n"
                    f"{EXCLAMATION_COMMANDS_INFO}\n"
                    "\n> **Dica**: experimente digitar `/credito` ou `!vote`, por exemplo!"
                ),
                color=discord.Color.green()
            )
            
            # Envia no canal onde a palavra-chave foi detectada
            await message.channel.send(embed=embed)


# Função para carregar o Cog
async def setup(bot: commands.Bot):
    await bot.add_cog(AjudaComandosCog(bot))
