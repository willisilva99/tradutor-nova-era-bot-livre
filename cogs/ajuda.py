import discord
from discord.ext import commands
import asyncio

# ===== Palavras-chave e textos de COMANDOS =====
KEYWORDS_COMANDOS = [
    "comandos do servidor",
    "qual comando",
    "como ganha drop",
    "comandos"
]

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

# ===== Palavras-chave e textos de ARMADURAS =====
KEYWORDS_ARMADURAS = [
    "armadura",
    "qual bonus da",
    "qual armadura",
    "qual set e"
]

def criar_embed_comandos() -> discord.Embed:
    """Cria um embed com os comandos do servidor."""
    embed = discord.Embed(
        title="Lista de Comandos do Servidor",
        description=f"{SLASH_COMMANDS_INFO}\n\n{EXCLAMATION_COMMANDS_INFO}",
        color=discord.Color.green()
    )
    embed.set_footer(text="Comandos do Servidor")
    return embed

def criar_embed_armaduras() -> discord.Embed:
    """Cria e retorna um Embed com as armaduras e seus conjuntos/bônus."""
    embed = discord.Embed(
        title="Guia de Armaduras",
        description="Confira os diferentes tipos de armaduras, seus bônus e conjuntos.",
        color=discord.Color.gold()
    )
    # Armadura Primitiva
    embed.add_field(
        name="🪖 Armadura Primitiva",
        value=(
            "**Não possui bônus de conjunto.**\n"
            "• Geralmente é a primeira que você encontra ou fabrica.\n"
            "• Dá uma defesa inicial, mas não espere nada além do básico."
        ),
        inline=False
    )
    # Armaduras Leves
    embed.add_field(
        name="☀️ Armaduras Leves",
        value=(
            "Ideais para quem quer mobilidade e foco em habilidades específicas sem perder velocidade."
        ),
        inline=False
    )
    embed.add_field(
        name="🪓 1) Conjunto Lumberjack",
        value=(
            "**Bônus Individuais**:\n"
            "• Aumenta a quantidade de madeira coletada.\n"
            "• Concede slots extras de inventário.\n"
            "• Melhora o dano com machados.\n"
            "• Reduz o consumo de estamina ao correr.\n"
            "**Bônus de Conjunto**: +100% de madeira e redução de 5%-30% no custo de estamina ao golpear."
        ),
        inline=False
    )
    embed.add_field(
        name="⛪ 2) Conjunto Preacher",
        value=(
            "**Bônus Individuais**:\n"
            "• Preços de compra mais baratos.\n"
            "• Menos dano sofrido de zumbis.\n"
            "• Maior dano causado a zumbis.\n"
            "• Ferimentos curam mais rápido.\n"
            "**Bônus de Conjunto**: Reduz chance de ferimentos críticos e pode zerar chance de infecção em Tier máximo!"
        ),
        inline=False
    )
    embed.add_field(
        name="🕵️ 3) Conjunto Rogue",
        value=(
            "**Bônus Individuais**:\n"
            "• Loot mais rápido e de melhor qualidade.\n"
            "• Furtividade aprimorada.\n"
            "• Lockpicking mais eficaz.\n"
            "• Queda de alturas maiores sem dano.\n"
            "**Bônus de Conjunto**: Até +30% de dinheiro/dukes encontrados."
        ),
        inline=False
    )
    embed.add_field(
        name="🏃 4) Conjunto Athletic",
        value=(
            "**Bônus Individuais**:\n"
            "• Itens de alimentação ficam mais baratos.\n"
            "• Aumento de vida máxima.\n"
            "• Aumento de estamina máxima.\n"
            "• Velocidade de corrida melhorada.\n"
            "**Bônus de Conjunto**: Regenerar saúde/estamina consome até 60% menos comida e água."
        ),
        inline=False
    )
    embed.add_field(
        name="🔫 5) Conjunto Enforcer",
        value=(
            "**Bônus Individuais**:\n"
            "• Melhores preços de compra e venda.\n"
            "• Resistência a ferimentos críticos.\n"
            "• Economia de combustível em veículos.\n"
            "• Velocidade de corrida melhorada.\n"
            "**Bônus de Conjunto**: Munição .44 causa até +50% de dano e recarrega +50% mais rápido."
        ),
        inline=False
    )
    # Armaduras Médias
    embed.add_field(
        name="⚔️ Armaduras Médias",
        value="Equilibram defesa e mobilidade, boas para quem quer versatilidade.",
        inline=False
    )
    embed.add_field(
        name="🌱 1) Conjunto Farmer",
        value=(
            "**Bônus Individuais**:\n"
            "• Chance maior de encontrar sementes.\n"
            "• Colheita com chance de itens extras.\n"
            "• Rifles causam mais dano.\n"
            "• Chance extra de sementes ao colher.\n"
            "**Bônus de Conjunto**: Comida/bebida curam até +40% de vida."
        ),
        inline=False
    )
    embed.add_field(
        name="🏍️ 2) Conjunto Biker",
        value=(
            "**Bônus Individuais**:\n"
            "• Resistência a atordoamentos.\n"
            "• Mais pontos de vida máxima.\n"
            "• Dano melee aumentado.\n"
            "• Menos estamina gasta ao bater.\n"
            "**Bônus de Conjunto**: Pontos extras de armadura e redução de combustível em motos."
        ),
        inline=False
    )
    embed.add_field(
        name="🔧 3) Conjunto Scavenger",
        value=(
            "**Bônus Individuais**:\n"
            "• Mais XP ao desmontar (salvaging).\n"
            "• Mais slots de inventário.\n"
            "• Chance de recursos extras ao desmontar.\n"
            "• Menos estamina ao usar ferramentas de sucata.\n"
            "**Bônus de Conjunto**: +20% na qualidade do loot encontrado."
        ),
        inline=False
    )
    embed.add_field(
        name="🏹 4) Conjunto Ranger",
        value=(
            "**Bônus Individuais**:\n"
            "• Melhores preços em negociações.\n"
            "• Mais pontos de vida máxima.\n"
            "• Maior dano com rifles de ação por alavanca e revolveres.\n"
            "• Mais estamina máxima.\n"
            "**Bônus de Conjunto**: Recarrega rifles/revolveres até 50% mais rápido."
        ),
        inline=False
    )
    embed.add_field(
        name="💣 5) Conjunto Commando",
        value=(
            "**Bônus Individuais**:\n"
            "• Resistência a atordoamentos.\n"
            "• Cura de ferimentos mais rápida.\n"
            "• Armas de fogo causam dano extra.\n"
            "• Corrida mais veloz.\n"
            "**Bônus de Conjunto**: Itens de cura funcionam até 50% mais rápido."
        ),
        inline=False
    )
    embed.add_field(
        name="🗡️ 6) Conjunto Assassin",
        value=(
            "**Bônus Individuais**:\n"
            "• Dano de ataque furtivo muito maior.\n"
            "• Melhor furtividade ao agachar.\n"
            "• Mais velocidade de ataque com armas de agilidade.\n"
            "• Corrida silenciosa ao agachar.\n"
            "**Bônus de Conjunto**: Inimigos desistem de te procurar até 100% mais rápido."
        ),
        inline=False
    )
    # Armaduras Pesadas
    embed.add_field(
        name="🛡️ Armaduras Pesadas",
        value="Maior proteção, mas mais peso e ruído. Boa para combate direto.",
        inline=False
    )
    embed.add_field(
        name="⛏️ 1) Conjunto Miner",
        value=(
            "**Bônus Individuais**:\n"
            "• Mais recursos ao minerar.\n"
            "• Menos estamina para ferramentas de mineração.\n"
            "• Quebra de blocos mais rápida.\n"
            "• Queda de alturas maiores sem dano.\n"
            "**Bônus de Conjunto**: Ferramentas de mineração desgastam -35%."
        ),
        inline=False
    )
    embed.add_field(
        name="🏜️ 2) Conjunto Nomad",
        value=(
            "**Bônus Individuais**:\n"
            "• Regenerar saúde/estamina gasta menos comida/água.\n"
            "• Mais slots de inventário.\n"
            "• Dano extra contra zumbis irradiados.\n"
            "• Corrida mais rápida.\n"
            "**Bônus de Conjunto**: Reduz ainda mais (até 30%) o custo de comida/água para regenerar."
        ),
        inline=False
    )
    embed.add_field(
        name="🧠 3) Conjunto Nerd",
        value=(
            "**Bônus Individuais**:\n"
            "• Ganha mais XP em tudo.\n"
            "• Chance de subir nível extra ao usar Revistas.\n"
            "• Turrets e batons elétricos causam mais dano.\n"
            "• Maior altura de queda segura.\n"
            "**Bônus de Conjunto**: Todas as ferramentas/armas gastam -35% de durabilidade."
        ),
        inline=False
    )
    embed.add_field(
        name="💀 4) Conjunto Raider",
        value=(
            "**Bônus Individuais**:\n"
            "• Resistência máxima a atordoamentos.\n"
            "• Ferimentos críticos se curam mais rápido.\n"
            "• Dano melee muito mais alto.\n"
            "• Maior altura de queda segura.\n"
            "**Bônus de Conjunto**: Até 45% de resistência a ferimentos críticos."
        ),
        inline=False
    )

    embed.set_footer(text="Armaduras de 7 Days to Die • Exemplo de Servidor")
    return embed


class PerguntaView(discord.ui.View):
    """View genérica com botões 'Sim' e 'Não'. Pergunta se quer ver algo (comandos ou armaduras)."""
    def __init__(
        self,
        embed: discord.Embed,
        timeout: float = 30.0,
        remover_msg_depois: float = 60.0
    ):
        """
        :param embed: O Embed a exibir caso o usuário clique em 'Sim'.
        :param timeout: Tempo (s) para os botões ficarem ativos.
        :param remover_msg_depois: Tempo (s) para remover a mensagem do embed após ser enviado.
        """
        super().__init__(timeout=timeout)
        self.message = None               # Referência à mensagem enviada com a pergunta
        self.embed = embed                # O embed a enviar se clicar em "Sim"
        self.remover_msg_depois = remover_msg_depois

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def botao_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Usuário quer ver o embed."""
        await interaction.response.defer(thinking=True)
        # Envia o embed
        msg_embed = await interaction.followup.send(embed=self.embed)
        
        # Remove a mensagem de pergunta
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        # Aguarda X segundos e então deleta o embed
        await asyncio.sleep(self.remover_msg_depois)
        try:
            await msg_embed.delete()
        except:
            pass

        self.stop()

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def botao_nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Usuário não quer ver o embed."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

    async def on_timeout(self):
        """Se ninguém clicar em nada após 'timeout' s, apaga a mensagem de pergunta."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()


class AjudaCompletaCog(commands.Cog):
    """Cog que detecta keywords para Comandos do Servidor ou Armaduras e pergunta com botões."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bot
        if message.author.bot:
            return

        content_lower = message.content.lower()

        # 1) Verifica se é sobre COMANDOS
        if any(keyword in content_lower for keyword in KEYWORDS_COMANDOS):
            embed_comandos = criar_embed_comandos()

            # Cria a view perguntando se quer ver os comandos
            view = PerguntaView(embed=embed_comandos, timeout=30.0, remover_msg_depois=60.0)

            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de COMANDOS do servidor?",
                view=view
            )
            view.message = sent
            return  # Evita cair no próximo if se a mensagem tiver as duas coisas

        # 2) Verifica se é sobre ARMADURAS
        if any(keyword in content_lower for keyword in KEYWORDS_ARMADURAS):
            embed_armaduras = criar_embed_armaduras()

            # Cria a view perguntando se quer ver as armaduras
            view = PerguntaView(embed=embed_armaduras, timeout=30.0, remover_msg_depois=60.0)

            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de ARMADURAS e seus bônus?",
                view=view
            )
            view.message = sent

# Função para carregar o Cog
async def setup(bot: commands.Bot):
    await bot.add_cog(AjudaCompletaCog(bot))
