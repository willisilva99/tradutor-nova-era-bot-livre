import discord
from discord.ext import commands
import asyncio

# Palavras-chave para acionar o guia de Arcano
KEYWORDS_ARCANO = [
    "arcano",
    "arcano z",
    "guia arcano",
    "onde conseguir arcano",
    "boss",
    "world-boss"
]

def criar_embed_arcano() -> discord.Embed:
    """Cria o embed com o Guia de Onde Conseguir Arcano e Arcano Z."""
    embed = discord.Embed(
        title="💰 Guia de Onde Conseguir Arcano e Arcano Z 💰",
        description=(
            "Olá, sobrevivente! Se você está atrás das preciosas moedas **Arcano** e **Arcano Z**, confira estas dicas essenciais para consegui-las no servidor. "
            "Essas moedas são fundamentais para quem quer avançar logo de primeira, especialmente matando boss e world-boss!\n\n"

            "⚔️ **Drops de Boss e World-Boss**\n"
            "• **Bosses Regulares**: Você pode obter Arcano e Arcano Z logo de primeira ao derrotar os boss que rodam pelo servidor.\n"
            "• **World-Boss**: O World-Boss possui impressionantes 1.000.000 HP e causa alto dano. Derrotá-lo garante um drop generoso dessas moedas, "
            "que são dropadas em grande quantidade.\n"
            "  *Dica*: Enfrente o World-Boss quando estiver bem equipado para maximizar seus ganhos!\n\n"

            "🗺️ **Locais de Drop**\n"
            "• **No Ermo**: É o local com a maior concentração dessas moedas. Atenção: Para acessar o ermo, é indispensável ter o mod de radiação na sua armadura "
            "e usar uma capa de chuva para se proteger.\n"
            "• **Outras Áreas Importantes**: Neve no Deserto e Floresta Queimada também oferecem chances de encontrar Arcano e Arcano Z.\n\n"

            "💡 **Outras Fontes para Obter as Moedas**\n"
            "• **Votando no Site**: Cada voto conta! Ao votar no site, você pode receber essas moedas como recompensa.\n"
            "• **Comando /vote**: Utilize o comando no jogo para garantir suas recompensas diretamente.\n"
            "• **Drops em Itens**: Em algumas ocasiões, sofás, TVs, computadores e parquímetros podem dropar Arcano e Arcano Z – embora com chances menores.\n\n"

            "🚀 **Dicas Finais para Maximizar Seus Ganhos**\n"
            "• **Prepare-se Adequadamente**: Antes de ir para o ermo, certifique-se de equipar seu personagem com o mod de radiação e uma capa de chuva para enfrentar as condições adversas.\n"
            "• **Trabalho em Equipe**: Se possível, enfrente o World-Boss com amigos para aumentar as chances de sucesso e dividir os ganhos!\n"
            "• **Explore Todos os Cantos**: Não se limite apenas ao ermo. Verifique também áreas como a neve do deserto e a floresta queimada para encontrar moedas extras.\n\n"

            "Boa sorte na sua jornada e que os drops sejam generosos! Se tiver mais dúvidas, não hesite em perguntar no canal de ajuda do Discord."
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Guia de Arcano e Arcano Z • 7 Days to Die")
    return embed

class ArcanoView(discord.ui.View):
    """
    View com botões "Sim" e "Não" para o guia de Arcano.
    - Se o usuário clicar em "Sim": envia o embed e apaga a mensagem de pergunta; o embed é removido após 1 minuto.
    - Se clicar em "Não" ou se expirar (30s): apaga a mensagem de pergunta.
    """
    def __init__(self, embed: discord.Embed, timeout: float = 30.0, remover_msg_depois: float = 60.0):
        super().__init__(timeout=timeout)
        self.message = None  # Guardará a mensagem da pergunta
        self.embed = embed
        self.remover_msg_depois = remover_msg_depois

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def botao_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        msg_embed = await interaction.followup.send(embed=self.embed)
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass
        await asyncio.sleep(self.remover_msg_depois)
        try:
            await msg_embed.delete()
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def botao_nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass
        self.stop()

class ArcanoCog(commands.Cog):
    """Cog exclusivo para o Guia de Onde Conseguir Arcano e Arcano Z."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bots
        if message.author.bot:
            return

        content_lower = message.content.lower()
        if any(keyword in content_lower for keyword in KEYWORDS_ARCANO):
            embed_arcano = criar_embed_arcano()
            view = ArcanoView(embed_arcano, timeout=30.0, remover_msg_depois=60.0)
            msg = await message.channel.send(
                f"{message.author.mention}, deseja ver o guia de onde conseguir Arcano e Arcano Z?",
                view=view
            )
            view.message = msg

async def setup(bot: commands.Bot):
    await bot.add_cog(ArcanoCog(bot))
