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


class ComandosView(discord.ui.View):
    """View com botões 'Sim' e 'Não' para exibir ou não os comandos."""
    def __init__(self, timeout: float = 30.0, embed_ajuda: discord.Embed = None):
        super().__init__(timeout=timeout)
        self.message = None       # Armazenará a mensagem com os botões
        self.embed_ajuda = embed_ajuda  # O embed com comandos que exibiremos se o usuário clicar em 'Sim'

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def botao_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Usuário quer ver os comandos."""
        # Manda o embed de ajuda no mesmo canal
        await interaction.response.send_message(embed=self.embed_ajuda)

        # Remove a mensagem original com os botões
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def botao_nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Usuário não quer ver os comandos."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

    async def on_timeout(self):
        """Após o tempo definido (30s), se ninguém clicar, apaga a mensagem."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()


class AjudaComandosCog(commands.Cog):
    """Quando detecta palavras-chave, pergunta se o usuário quer ver a lista de comandos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bot
        if message.author.bot:
            return
        
        content_lower = message.content.lower()
        if any(keyword in content_lower for keyword in KEYWORDS):
            # Cria o embed
            embed_ajuda = discord.Embed(
                title="Lista de Comandos do Servidor",
                description=f"{SLASH_COMMANDS_INFO}\n\n{EXCLAMATION_COMMANDS_INFO}",
                color=discord.Color.green()
            )

            # Cria a view com botões
            view = ComandosView(embed_ajuda=embed_ajuda)

            # Envia a mensagem perguntando "Quer ver os comandos?"
            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de comandos do servidor?",
                view=view
            )

            # Armazena a mensagem no objeto da view para poder deletá-la depois
            view.message = sent


async def setup(bot: commands.Bot):
    await bot.add_cog(AjudaComandosCog(bot))
