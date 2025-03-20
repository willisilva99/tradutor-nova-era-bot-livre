import discord
from discord.ext import commands
import asyncio

# ======================[ 1) Comandos do Servidor ]======================

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

def criar_embed_comandos() -> discord.Embed:
    """Cria um embed com os comandos do servidor."""
    embed = discord.Embed(
        title="Lista de Comandos do Servidor",
        description=f"{SLASH_COMMANDS_INFO}\n\n{EXCLAMATION_COMMANDS_INFO}",
        color=discord.Color.green()
    )
    embed.set_footer(text="Comandos do Servidor")
    return embed

# ======================[ 2) Armaduras ]======================

KEYWORDS_ARMADURAS = [
    "armadura",
    "qual bonus da",
    "qual armadura",
    "qual set e"
]

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
            "**Bônus de Conjunto**: +100% de madeira e redução de 5%-30% no custo de estamina."
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
            "• Loot mais rápido e melhor.\n"
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
            "• Aumento de vida e estamina máxima.\n"
            "• Velocidade de corrida melhorada.\n"
            "**Bônus de Conjunto**: Regenerar saúde e estamina consome até 60% menos comida e água."
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
            "**Bônus de Conjunto**: Munição .44 causa até +50% de dano e recarrega até +50% mais rápido."
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
            "• Colheita de plantação com chance de itens extras.\n"
            "• Rifles causam mais dano.\n"
            "• Chance extra de sementes.\n"
            "**Bônus de Conjunto**: Comida e bebida curam até +40% de vida adicional."
        ),
        inline=False
    )
    embed.add_field(
        name="🏍️ 2) Conjunto Biker",
        value=(
            "**Bônus Individuais**:\n"
            "• Resistência a atordoamentos.\n"
            "• Mais pontos de vida máxima.\n"
            "• Dano corpo a corpo aumentado.\n"
            "• Menos estamina gasta ao bater.\n"
            "**Bônus de Conjunto**: Garante pontos extras na armadura e reduz gasto de combustível em motos."
        ),
        inline=False
    )
    embed.add_field(
        name="🔧 3) Conjunto Scavenger",
        value=(
            "**Bônus Individuais**:\n"
            "• Mais XP ao desmontar.\n"
            "• Mais slots de inventário.\n"
            "• Chance de recursos extras ao desmontar.\n"
            "• Menos estamina ao usar ferramentas de sucata.\n"
            "**Bônus de Conjunto**: Aumenta a qualidade do loot encontrado (até +20%)."
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
            "**Bônus de Conjunto**: Recarrega rifles de ação por alavanca e revolveres até 50% mais rápido."
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
            "• Corrida (sprint) mais veloz.\n"
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
        value="Maior proteção, mas também mais peso e ruído. Boa para combate direto ou defesa sólida.",
        inline=False
    )
    embed.add_field(
        name="⛏️ 1) Conjunto Miner",
        value=(
            "**Bônus Individuais**:\n"
            "• Mais recursos ao minerar.\n"
            "• Menos estamina para usar ferramentas de mineração.\n"
            "• Quebra de blocos mais rápida.\n"
            "• Queda de alturas maiores sem dano.\n"
            "**Bônus de Conjunto**: Ferramentas de mineração desgastam até 35% menos."
        ),
        inline=False
    )
    embed.add_field(
        name="🏜️ 2) Conjunto Nomad",
        value=(
            "**Bônus Individuais**:\n"
            "• Regenerar saúde/estamina consome menos comida e água.\n"
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
            "• Ganha mais experiência (XP) em tudo.\n"
            "• Chance de subir nível extra ao usar Revistas.\n"
            "• Turrets e cacetes elétricos causam mais dano.\n"
            "• Maior altura de queda segura.\n"
            "**Bônus de Conjunto**: Todas as ferramentas e armas gastam até 35% menos durabilidade."
        ),
        inline=False
    )
    embed.add_field(
        name="💀 4) Conjunto Raider",
        value=(
            "**Bônus Individuais**:\n"
            "• Resistência máxima a atordoamentos.\n"
            "• Ferimentos críticos se curam mais rápido.\n"
            "• Dano corpo a corpo muito mais alto.\n"
            "• Maior altura de queda segura.\n"
            "**Bônus de Conjunto**: Até 45% de resistência a ferimentos críticos."
        ),
        inline=False
    )

    embed.set_footer(text="Armaduras de 7 Days to Die • Exemplo de Servidor")
    return embed

# ======================[ 3) Veículos com Emojis e Imagem ]======================

KEYWORDS_VEICULOS = [
    "como fabrica carro",
    "aonde acho veiculo",
    "como fabrico minha moto",
    "veiculo"
]

def criar_embed_veiculos() -> discord.Embed:
    """Cria um embed grande, com emojis e uma imagem final, descrevendo os veículos."""
    embed = discord.Embed(
        title="🚗 Guia de Veículos",
        description=(
            "Veículos são essenciais na nossa jornada pela sobrevivência, seja para transportar recursos ou explorar.\n\n"
            "A seguir, veja **cinco** tipos de veículos, como construí-los e seus usos."
        ),
        color=discord.Color.blue()
    )

    # Adicionamos uma imagem de fundo (ou no topo)
    # A imagem aparecerá maior se estiver em .set_image() em vez de .set_thumbnail()
    embed.set_image(url="https://imgur.com/zPqLmH8.jpg")

    # Introdução
    embed.add_field(
        name="🚀 Introdução",
        value=(
            "Com veículos podemos explorar novos lugares e trazer recursos para nossa base com mais facilidade.\n"
            "Temos Bicicleta, Minimoto, Moto, 4x4 (Jipe) e Girocóptero!"
        ),
        inline=False
    )

    # Bicicleta
    embed.add_field(
        name="🚲 Bicicleta",
        value=(
            "• Conquistada na primeira semana ou como recompensa de missões Tier 1.\n"
            "• Gasta estamina ao pedalar.\n"
            "• Dá mobilidade inicial, mas limitada."
        ),
        inline=False
    )

    # Minimoto
    embed.add_field(
        name="🏍️ Minimoto",
        value=(
            "• Feita com chassi, guidão, rodas, motor e bateria.\n"
            "• Usa barras de ferro para fabricar chassi/guidão.\n"
            "• Ideal até ~2ª semana (dia 8-14)."
        ),
        inline=False
    )

    # Moto
    embed.add_field(
        name="🏍️ Moto",
        value=(
            "• Parecida com a minimoto, mas usa **barras de aço**.\n"
            "• Boa agilidade, armazenamento razoável.\n"
            "• Consome combustível moderado e é ótima para exploração urbana."
        ),
        inline=False
    )

    # 4x4
    embed.add_field(
        name="🚙 Jipe 4x4",
        value=(
            "• Maior armazenamento (81 slots), ideal para longas viagens.\n"
            "• Até 4 assentos (ou 6, dependendo do server).\n"
            "• Consome muito combustível, mas carrega tudo."
        ),
        inline=False
    )

    # Girocóptero
    embed.add_field(
        name="✈️ Girocóptero",
        value=(
            "• O mais rápido, pois voa (15 m/s).\n"
            "• Requer prática para decolar/pousar.\n"
            "• Excelente para longas distâncias e visitar mercadores."
        ),
        inline=False
    )

    # Tabela resumida
    embed.add_field(
        name="📝 Informações Detalhadas",
        value=(
            "**Bicicleta** — Durab: 1500, Vel: 8 m/s, Armaz: 9, Comb: 0, Assento:1\n"
            "**Minimoto** — Durab: 2000, Vel: 9 m/s, Armaz: 27, Comb: 1000, Assento:1\n"
            "**Moto** — Durab: 4000, Vel: 14 m/s, Armaz: 36, Comb: 3000, Assento:1\n"
            "**4x4** — Durab: 8000, Vel: 14 m/s, Armaz: 81, Comb: 10000, Assentos:4\n"
            "**Giro** — Durab: 3500, Vel: 15 m/s, Armaz: 45, Comb: 2000, Assentos:2"
        ),
        inline=False
    )

    # Modificações
    embed.add_field(
        name="🔧 Modificações",
        value=(
            "• **Super Carregador** aumenta velocidade.\n"
            "• **Economizador de Combustível** reduz consumo.\n"
            "• **Tanque Reserva** aumenta capacidade.\n"
            "• **Charrua/Blindagem** protegem contra danos.\n"
            "• Cada veículo tem limite de 'slots' de mod."
        ),
        inline=False
    )

    # Sendo um bom mecânico
    embed.add_field(
        name="🧰 Sendo um bom mecânico",
        value=(
            "• Habilidades de *Mecânica* podem reduzir custo de fabricação em 33%.\n"
            "• Revistas desbloqueiam chassi, guidões, combustíveis em pilha.\n"
            "• Kits de reparo são essenciais pra tudo (não esqueça de fabricar!)."
        ),
        inline=False
    )

    # Trajes para condução
    embed.add_field(
        name="🩼 Trajes para condução",
        value=(
            "• **Traje de Motoqueiro**: reduz consumo de combustível em até -20% (usando o conjunto completo).\n"
            "• **Traje de Executor**: basta usar as luvas para reduzir combustível (até -20%).\n"
            "• Você escolhe o estilo que combina com seu personagem!"
        ),
        inline=False
    )

    # Mercador Bob
    embed.add_field(
        name="🛒 Mercador 'Bob'",
        value=(
            "• Normalmente o 3º mercador desbloqueado.\n"
            "• Especialista em itens mecânicos e peças veiculares.\n"
            "• Pode vender até mesmo veículos prontos!"
        ),
        inline=False
    )

    embed.set_footer(text="Veículos em 7 Days to Die • Exemplo de Servidor")
    return embed

# ======================[ VIEW COM BOTÕES ]======================

class PerguntaView(discord.ui.View):
    """
    View com botões 'Sim' e 'Não', usada para perguntar se o usuário quer ver determinado Embed.
    Ao clicar em 'Sim', envia o embed, apaga a pergunta e remove o embed após 1 minuto.
    Ao clicar em 'Não' ou se expirar em 30s, apaga a mensagem de pergunta.
    """
    def __init__(self, embed: discord.Embed, timeout: float = 30.0, remover_msg_depois: float = 60.0):
        super().__init__(timeout=timeout)
        self.message = None               # Mensagem com a pergunta
        self.embed = embed                # Embed a enviar se clicar em "Sim"
        self.remover_msg_depois = remover_msg_depois

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def botao_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        # Envia o embed
        msg_embed = await interaction.followup.send(embed=self.embed)

        # Remove a mensagem (pergunta) original
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        # Aguardar X segundos e deletar o embed
        await asyncio.sleep(self.remover_msg_depois)
        try:
            await msg_embed.delete()
        except:
            pass

        self.stop()

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def botao_nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

    async def on_timeout(self):
        """Se ninguém clicar em nada após 'timeout' (30s), a pergunta é apagada."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

# ======================[ COG PRINCIPAL ]======================

class AjudaCompletaCog(commands.Cog):
    """Cog que detecta keywords para: Comandos do Servidor, Armaduras e Veículos;
       então pergunta com botões se o usuário quer ver essas infos.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bot
        if message.author.bot:
            return

        content_lower = message.content.lower()

        # Verifica se é sobre COMANDOS
        if any(keyword in content_lower for keyword in KEYWORDS_COMANDOS):
            embed_comandos = criar_embed_comandos()
            view = PerguntaView(embed=embed_comandos, timeout=30.0, remover_msg_depois=60.0)
            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de COMANDOS do servidor?",
                view=view
            )
            view.message = sent
            return  # Evita cair em outras checagens se bateu nessa

        # Verifica se é sobre ARMADURAS
        if any(keyword in content_lower for keyword in KEYWORDS_ARMADURAS):
            embed_armaduras = criar_embed_armaduras()
            view = PerguntaView(embed=embed_armaduras, timeout=30.0, remover_msg_depois=60.0)
            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de ARMADURAS e seus bônus?",
                view=view
            )
            view.message = sent
            return

        # Verifica se é sobre VEÍCULOS
        if any(keyword in content_lower for keyword in KEYWORDS_VEICULOS):
            embed_veiculos = criar_embed_veiculos()
            view = PerguntaView(embed=embed_veiculos, timeout=30.0, remover_msg_depois=60.0)
            sent = await message.channel.send(
                f"{message.author.mention}, deseja ver as informações sobre VEÍCULOS?",
                view=view
            )
            view.message = sent
            return


async def setup(bot: commands.Bot):
    """Função para carregar o Cog no bot."""
    await bot.add_cog(AjudaCompletaCog(bot))
