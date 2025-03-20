import discord
from discord.ext import commands
import asyncio

# ===================================================
# ================ 1) COMANDOS ======================
# ===================================================

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
    "`/arena` - Teleporta você até a arena PvP (Player vs Player).\n"
    "`/drone` - Exibe localização do drone perdido.\n"
    "`/reset` - Reseta seu personagem, apagando tudo e começando do zero.\n"
    "`/claim` - Resgata itens do site que você comprou."
)

EXCLAMATION_COMMANDS_INFO = (
    "**Comandos com Exclamação (!)**\n"
    "`!vote` - Abre o site de votação.\n"
    "`!amigo [nome]` - Teleporta você até o amigo especificado.\n"
    "`!discord` - Entra no Discord do servidor.\n"
    "`!loteria` - Exibe as informações da loteria de dukes.\n"
    "`!loteria entrar` - Entra na loteria com 1000 dukes.\n"
    "`!loc` - Exibe sua localização.\n"
    "`!fps` - Mostra seu FPS (frames por segundo).\n"
    "`!bug` - Se estiver preso em um bug, utiliza para sair dessa situação.\n"
    "`!killme` - Mata seu personagem.\n"
    "`!suicide` - Executa o comando para suicídio do personagem."
)

def criar_embed_comandos() -> discord.Embed:
    """Embed completo para os Comandos do Servidor."""
    embed = discord.Embed(
        title="Lista de Comandos do Servidor",
        description=(
            f"{SLASH_COMMANDS_INFO}\n\n"
            f"{EXCLAMATION_COMMANDS_INFO}\n"
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text="Comandos do Servidor • 7 Days to Die")
    return embed


# ===================================================
# ================ 2) ARMADURAS =====================
# ===================================================

KEYWORDS_ARMADURAS = [
    "armadura",
    "qual bonus da",
    "qual armadura",
    "qual set e"
]

def criar_embed_armaduras() -> discord.Embed:
    """Embed completo para Armaduras."""
    embed = discord.Embed(
        title="Guia de Armaduras",
        description="Confira cada tipo de armadura, seus bônus e conjuntos.",
        color=discord.Color.gold()
    )

    # Texto extenso das armaduras (conforme enviado pelo usuário)
    texto_armaduras = (
        "🪖 **Armadura Primitiva**\n"
        "Não possui bônus de conjunto.\n"
        "Geralmente é a primeira que você encontra ou fabrica.\n"
        "Dá uma defesa inicial, mas não espere nada além do básico.\n\n"

        "☀️ **Armaduras Leves**\n"
        "Ideais para quem quer mobilidade e foco em habilidades específicas sem perder velocidade.\n\n"

        "🪓 **1) Conjunto Lumberjack**\n"
        "**Bônus Individuais**:\n"
        "• Aumenta a quantidade de madeira coletada.\n"
        "• Concede slots extras de inventário.\n"
        "• Melhora o dano com machados.\n"
        "• Reduz o consumo de estamina ao correr.\n"
        "**Bônus de Conjunto**: +100% de madeira ao colher com machado e redução de 5% a 30% no custo de estamina ao golpear.\n\n"

        "⛪ **2) Conjunto Preacher**\n"
        "**Bônus Individuais**:\n"
        "• Preços de compra mais baratos.\n"
        "• Menos dano sofrido de zumbis.\n"
        "• Maior dano causado a zumbis.\n"
        "• Ferimentos curam mais rápido.\n"
        "**Bônus de Conjunto**: Reduz a chance de ferimentos críticos e pode até zerar a chance de infecção em Tier máximo!\n\n"

        "🕵️ **3) Conjunto Rogue**\n"
        "**Bônus Individuais**:\n"
        "• Saque (loot) mais rápido e com qualidade melhor.\n"
        "• Furtividade aprimorada (dificulta ser detectado).\n"
        "• Lockpicking mais eficaz (menos tempo e menos quebras de lockpick).\n"
        "• Queda de alturas maiores sem receber dano.\n"
        "**Bônus de Conjunto**: Até +30% de dinheiro e dukes encontrados em loot.\n\n"

        "🏃 **4) Conjunto Athletic**\n"
        "**Bônus Individuais**:\n"
        "• Itens de alimentação (comida, bebida, drogas) ficam mais baratos.\n"
        "• Aumento de vida máxima (HP).\n"
        "• Aumento de estamina máxima.\n"
        "• Velocidade de corrida melhorada.\n"
        "**Bônus de Conjunto**: Regenerar saúde e estamina consome até 60% menos comida e água.\n\n"

        "🔫 **5) Conjunto Enforcer**\n"
        "**Bônus Individuais**:\n"
        "• Melhores preços de compra e venda.\n"
        "• Resistência a ferimentos críticos.\n"
        "• Economia de combustível em veículos.\n"
        "• Velocidade de corrida melhorada.\n"
        "**Bônus de Conjunto**: Munição .44 causa até +50% de dano e as armas (Magnum/Desert Vulture) recarregam até +50% mais rápido.\n\n"

        "⚔️ **Armaduras Médias**\n"
        "Equilibram defesa e mobilidade, boas para quem quer versatilidade.\n\n"

        "🌱 **1) Conjunto Farmer**\n"
        "**Bônus Individuais**:\n"
        "• Chance maior de encontrar sementes em loot.\n"
        "• Colheita de plantação com chance de itens extras.\n"
        "• Rifles causam mais dano.\n"
        "• Chance de ganhar sementes extras ao colher.\n"
        "**Bônus de Conjunto**: Comida e bebida curam até +40% de vida adicional.\n\n"

        "🏍️ **2) Conjunto Biker**\n"
        "**Bônus Individuais**:\n"
        "• Resistência a atordoamentos.\n"
        "• Mais pontos de vida máxima.\n"
        "• Dano corpo a corpo (melee) aumentado.\n"
        "• Menos estamina gasta ao bater com arma branca.\n"
        "**Bônus de Conjunto**: Garante pontos extras na armadura e reduz gasto de combustível em motos e minibikes.\n\n"

        "🔧 **3) Conjunto Scavenger**\n"
        "**Bônus Individuais**:\n"
        "• Mais XP ao desmontar (salvaging).\n"
        "• Mais slots de inventário.\n"
        "• Chance de ganhar recursos extras ao desmontar.\n"
        "• Menos estamina ao usar ferramentas de sucata.\n"
        "**Bônus de Conjunto**: Aumenta a qualidade do loot encontrado (até +20%).\n\n"

        "🏹 **4) Conjunto Ranger**\n"
        "**Bônus Individuais**:\n"
        "• Melhores preços em negociações.\n"
        "• Mais pontos de vida máxima.\n"
        "• Maior dano com rifles de ação por alavanca e revolveres.\n"
        "• Mais estamina máxima.\n"
        "**Bônus de Conjunto**: Recarregue rifles de ação por alavanca e revolveres até 50% mais rápido.\n\n"

        "💣 **5) Conjunto Commando**\n"
        "**Bônus Individuais**:\n"
        "• Resistência a atordoamentos.\n"
        "• Cura de ferimentos mais rápida.\n"
        "• Armas de fogo causam dano extra.\n"
        "• Corrida (sprint) mais veloz.\n"
        "**Bônus de Conjunto**: Itens de cura funcionam até 50% mais rápido.\n\n"

        "🗡️ **6) Conjunto Assassin**\n"
        "**Bônus Individuais**:\n"
        "• Dano de ataque furtivo (sneak) muito maior.\n"
        "• Melhor furtividade e movimento ao se agachar.\n"
        "• Mais velocidade de ataque com armas de agilidade (facas, arcos, etc.).\n"
        "• Corrida silenciosa ao agachar (sem barulho adicional).\n"
        "**Bônus de Conjunto**: Inimigos desistem de te procurar até 100% mais rápido depois que você some da visão deles.\n\n"

        "🛡️ **Armaduras Pesadas**\n"
        "Maior proteção, mas também mais peso e ruído. Boa para quem gosta de combate direto ou precisa de defesa sólida.\n\n"

        "⛏️ **1) Conjunto Miner**\n"
        "**Bônus Individuais**:\n"
        "• Mais recursos ao minerar.\n"
        "• Menos estamina para usar ferramentas de mineração.\n"
        "• Quebra de blocos (minério) mais rápida.\n"
        "• Queda de alturas maiores sem dano.\n"
        "**Bônus de Conjunto**: Ferramentas de mineração desgastam até 35% menos.\n\n"

        "🏜️ **2) Conjunto Nomad**\n"
        "**Bônus Individuais**:\n"
        "• Regenerar saúde/estamina consome menos comida e água.\n"
        "• Mais slots de inventário.\n"
        "• Dano extra contra zumbis irradiados.\n"
        "• Corrida (sprint) mais rápida.\n"
        "**Bônus de Conjunto**: Reduz ainda mais (até 30%) o custo de comida/água para regenerar.\n\n"

        "🧠 **3) Conjunto Nerd**\n"
        "**Bônus Individuais**:\n"
        "• Ganha mais experiência (XP) em tudo.\n"
        "• Chance de subir nível extra ao usar Revistas de Habilidade.\n"
        "• Turrets e cacetes elétricos (batons) causam mais dano.\n"
        "• Maior altura de queda segura.\n"
        "**Bônus de Conjunto**: Todas as ferramentas e armas gastam até 35% menos durabilidade.\n\n"

        "💀 **4) Conjunto Raider**\n"
        "**Bônus Individuais**:\n"
        "• Resistência máxima a atordoamentos.\n"
        "• Ferimentos críticos se curam mais rápido.\n"
        "• Dano corpo a corpo muito mais alto.\n"
        "• Maior altura de queda segura.\n"
        "**Bônus de Conjunto**: Até 45% de resistência a ferimentos críticos.\n"
    )

    embed.add_field(
        name="Armaduras Detalhadas",
        value=texto_armaduras,
        inline=False
    )

    embed.set_footer(text="Armaduras de 7 Days to Die • Exemplo de Servidor")
    return embed


# ===================================================
# ================ 3) VEÍCULOS ======================
# ===================================================

KEYWORDS_VEICULOS = [
    "como fabrica carro",
    "aonde acho veiculo",
    "como fabrico minha moto",
    "veiculo"
]

def criar_embed_veiculos() -> discord.Embed:
    """Embed completo de Veículos, usando texto integral fornecido."""
    embed = discord.Embed(
        title="🚗 Guia de Veículos",
        description=(
            "Veículos são essenciais na nossa jornada pela sobrevivência, eles nos levam a novos lugares, "
            "novas cidades, novos mercadores, novos horizontes a serem explorados..."
        ),
        color=discord.Color.blue()
    )
    embed.set_image(url="https://imgur.com/zPqLmH8.jpg")  # Imagem ilustrativa

    # Dividimos o texto em campos para não estourar limite de embed
    texto_introducao = (
        "**Introdução**\n"
        "Quem disse que sobreviver seria fácil? Precisamos nos esforçar para nos mantermos vivos, explorar, fazer nossas "
        "próprias armas, itens e o possível, mas nem tudo pode ser feito apenas com nossas próprias mãos... "
        "precisamos de estações de trabalho e **veículos** que ajudem nessa jornada.\n"
        "Podemos trazer com segurança nossos recursos para a base. "
        "Nesse guia, estarão as diferenças entre cada veículo, como construí-los e seus usos mais comuns!"
    )
    embed.add_field(name="Introdução", value=texto_introducao, inline=False)

    texto_quais = (
        "**Quais nossos veículos?**\n"
        "Temos 5 veículos diferentes (Bicicleta, Minimoto, Moto, Jipe 4x4 e Girocóptero). "
        "A construção e obtenção de materiais podem parecer difíceis no início, mas com as ferramentas certas "
        "e sabendo onde procurar, você poderá se aventurar facilmente."
    )
    embed.add_field(name="Veículos Disponíveis", value=texto_quais, inline=False)

    texto_bicicleta = (
        "**Bicicleta**\n\n"
        "A bicicleta é o nosso primeiro meio de transporte, podemos consegui-la já na primeira semana "
        "(recompensa de missões Tier 1 do mercador) ou fabricar com chassi e guidão. "
        "Usa estamina para pedalar (Shift), mas ajuda muito a explorar no começo."
    )
    embed.add_field(name="🚲 Bicicleta", value=texto_bicicleta, inline=False)

    texto_minimoto = (
        "**Minimoto**\n\n"
        "Após alguns dias conseguimos fazer a minimoto, feita com chassi, guidão, rodas, motor e bateria. "
        "Precisa de barras de ferro, peças mecânicas/elétricas, motores e baterias (obtidas ao desmontar veículos). "
        "É ideal até a segunda semana (dia 8-14)."
    )
    embed.add_field(name="🏍️ Minimoto", value=texto_minimoto, inline=False)

    texto_moto = (
        "**Moto**\n\n"
        "Favorita de muitos, ágil, bom armazenamento, não consome tanto combustível. "
        "Feita com chassi, guidão (ambos de aço), rodas, motor e bateria. "
        "Ótima para exploração urbana."
    )
    embed.add_field(name="🏍️ Moto", value=texto_moto, inline=False)

    texto_jipe = (
        "**Jipe 4x4**\n\n"
        "Melhor para transporte de cargas, com 81 slots de armazenamento e até 4 assentos. "
        "Exige barras de aço, 4 rodas, acessórios veiculares, motor e bateria. "
        "Consome muito combustível, mas leva toneladas de itens."
    )
    embed.add_field(name="🚙 Jipe 4x4", value=texto_jipe, inline=False)

    texto_giro = (
        "**Girocóptero**\n\n"
        "O mais rápido dos veículos, pois voa (15 m/s). "
        "Porém, é frágil e exige prática para pilotar. "
        "Ótimo para viagens longas, como buscar xisto no deserto ou visitar vários mercadores."
    )
    embed.add_field(name="✈️ Girocóptero", value=texto_giro, inline=False)

    texto_tabela = (
        "**Informações Detalhadas:**\n\n"
        "Bicicleta: Durabilidade 1500, Veloc. 8 m/s, Armaz. 9, Comb. 0, Assentos 1\n"
        "Minimoto: Durabilidade 2000, Veloc. 9 m/s, Armaz. 27, Comb. 1000, Assentos 1\n"
        "Moto: Durabilidade 4000, Veloc. 14 m/s, Armaz. 36, Comb. 3000, Assentos 1\n"
        "4x4: Durabilidade 8000, Veloc. 14 m/s, Armaz. 81, Comb. 10000, Assentos 4\n"
        "Giro: Durabilidade 3500, Veloc. 15 m/s, Armaz. 45, Comb. 2000, Assentos 2\n\n"
        "Comparando, o 4x4 se destaca em durabilidade, armazenamento e assentos, mas consome mais combustível. "
        "A moto é excelente no mid-game, equilibrando consumo e agilidade. "
        "O girocóptero é muito rápido, mas requer cuidado para decolar e pousar."
    )
    embed.add_field(name="Tabela Resumida", value=texto_tabela, inline=False)

    texto_mods = (
        "**Modificações**\n\n"
        "Podem reduzir consumo de combustível, aumentar velocidade, adicionar blindagem ou assentos extras. "
        "Cada veículo tem um número definido de slots para modificadores (bicicleta 2, minimoto 3, moto 4, 4x4 5, giro 4)."
    )
    embed.add_field(name="Modificações", value=texto_mods, inline=False)

    texto_sendo_mecanico = (
        "**Sendo um bom mecânico**\n\n"
        "Habilidades e revistas permitem fabricar chassi, guidões, combustível em pilhas (economizam 60% de xisto), etc. "
        "Baterias de nível baixo podem ser usadas nos veículos; as de nível alto, em instalações elétricas. "
        "Kits de reparo consertam qualquer veículo/ferramenta/arma."
    )
    embed.add_field(name="Habilidades e Manutenção", value=texto_sendo_mecanico, inline=False)

    texto_trajes = (
        "**Trajes para condução**\n\n"
        "• Traje de motoqueiro: usando o conjunto completo, reduz consumo de combustível em minimoto/moto. "
        "• Traje de executor: basta as luvas para reduzir consumo em todos os veículos. "
        "Varia de -2% até -20%, conforme o nível do traje."
    )
    embed.add_field(name="Trajes de Motoqueiro/Executor", value=texto_trajes, inline=False)

    texto_mercador = (
        "**Mercador 'Bob'**\n\n"
        "Geralmente o terceiro mercador desbloqueado. "
        "Especializado em itens mecânicos e peças de veículos. "
        "Pode vender peças, acessórios e até veículos completos."
    )
    embed.add_field(name="Mercador Bob", value=texto_mercador, inline=False)

    embed.set_footer(text="Veículos em 7 Days to Die • Exemplo de Servidor")
    return embed


# ===================================================
# ========== 4) ESTAÇÕES DE TRABALHO =================
# ===================================================

KEYWORDS_ESTACOES = [
    "estação de trabalhado",
    "estacao de trabalho",
    "forja"
]

def criar_embed_estacoes() -> discord.Embed:
    """Embed COMPLETO de Estações de Trabalho, usando o texto integral que o usuário forneceu."""
    embed = discord.Embed(
        title="⚙️ Estações de Trabalho e Forja",
        description=(
            "Quem disse que sobreviver seria fácil? Precisamos de fogueiras, forjas, bancadas, etc. "
            "para produzir nossos itens, comida, munições e muito mais!"
        ),
        color=discord.Color.orange()
    )

    # Quebramos o texto em vários fields para não ultrapassar limites do Discord
    # Texto original do usuário
    texto_intro = (
        "**Introdução**\n"
        "Quem disse que sobreviver seria fácil? Precisamos nos esforçar para nos mantermos vivos, explorar, "
        "fazer nossas próprias armas e itens. Nem tudo pode ser feito somente com as mãos...\n"
        "Precisamos de estações de trabalho para cozinhar alimentos, produzir armas, pólvora, ferro, concreto, "
        "e até mesmo obter água.\n\n"
        "Se estava buscando alguém para te ajudar... vamos começar!"
    )
    embed.add_field(name="Introdução", value=texto_intro, inline=False)

    texto_fogueira = (
        "**Fogueira**\n"
        "Iniciando pela estação mais básica, montada apenas com algumas pedras. "
        "Usada principalmente para alimentação, é preciso ter ao menos uma.\n\n"
        "Nela se faz comidas, bebidas e alguns itens de química (como cola e antibióticos).\n"
        "• Receitas simples não precisam de utensílios.\n"
        "• Receitas avançadas pedem panela ou grelha (encontre em cozinhas).\n"
        "• Gera calor (atrai zumbis) e pode te queimar se passar por cima!\n"
    )
    embed.add_field(name="Fogueira", value=f"{texto_fogueira}", inline=False)

    texto_coletor = (
        "**Coletor de orvalho**\n"
        "Responsável por coletar água automaticamente (até 3 garrafas). "
        "Certifique-se de esvaziá-lo para ele continuar coletando.\n\n"
        "• A água coletada vem turva; ferva antes de usar.\n"
        "• Pode ser melhorado com modificadores (coletor, lona e filtro). "
        "Ex.: aumentar velocidade, capacidade e purificar a água.\n"
        "• Necessita fita adesiva, canos e polímero de sucata para construir."
    )
    embed.add_field(name="Coletor de orvalho", value=texto_coletor, inline=False)

    texto_forja = (
        "**Forja**\n"
        "Essencial para construirmos itens intermediários e avançados (ferro, aço, cimento, munição...).\n\n"
        "• Precisamos \"derreter\" minérios antes de produzir barras ou pontas.\n"
        "• Recomenda-se ter 3 forjas dedicadas (ferro, munição e cimento).\n"
        "• Usa fole, bigorna e cadinho como modificadores.\n"
        "• O cadinho libera produção de aço e vidro blindado."
    )
    embed.add_field(name="Forja", value=texto_forja, inline=False)

    texto_bancada = (
        "**Bancada**\n"
        "Usada para montagem de armas, armaduras, ferramentas, veículos, modificações, etc.\n\n"
        "• Feita com ferro fundido, peças mecânicas, fita adesiva, pregos e madeira.\n"
        "• Ter ao menos duas ajuda a produzir itens em paralelo (economiza tempo)."
    )
    embed.add_field(name="Bancada", value=texto_bancada, inline=False)

    texto_betoneira = (
        "**Betoneira**\n"
        "Responsável pela produção de concreto.\n\n"
        "• Feita principalmente com peças mecânicas, barras de ferro, motor e molas.\n"
        "• Duas betoneiras ajudam, pois concreto leva tempo.\n"
        "• Pode transformar pedras em areia se estiver longe do deserto."
    )
    embed.add_field(name="Betoneira", value=texto_betoneira, inline=False)

    texto_quimica = (
        "**Estação de química**\n"
        "Produz principalmente combustível, pólvora e medicamentos.\n\n"
        "• Necessita proveta (Becker), barras de ferro, panelas, canos e garrafas de ácido.\n"
        "• Receitas químicas ficam mais baratas que na fogueira.\n"
        "• Ideal ter 1 ou 2 para produções em larga escala."
    )
    embed.add_field(name="Estação de química", value=texto_quimica, inline=False)

    texto_revistas = (
        "**Revistas e desbloqueio**\n"
        "\"Forja e Cia\" aumenta nível de fabricação de estações.\n\n"
        "• 05/75: Podemos produzir ferro na forja.\n"
        "• 10/75: Liberamos bancada, fole, bigorna e gázuas.\n"
        "• 30/75: Produzimos concreto (betoneira).\n"
        "• 50/75: Liberamos estação de química.\n"
        "• 75/75: Liberamos cadinho (produzir aço)."
    )
    embed.add_field(name="Revistas e desbloqueio", value=texto_revistas, inline=False)

    texto_otimizando = (
        "**Otimizando nossa produção**\n\n"
        "Precisamos de habilidades para cozinhar mais rápido, produzir ferro/aço e munição com menos recursos, etc.\n\n"
        "• **Mestre Cuca (Força)**: +velocidade ao cozinhar e -ingredientes necessários.\n"
        "• **Engenharia Avançada (Intelecto)**: +velocidade em forjas/bancadas, economia de materiais, "
        "e XP ao matar zumbis com armadilhas elétricas."
    )
    embed.add_field(name="Otimizando a Produção", value=texto_otimizando, inline=False)

    embed.set_footer(text="Estações de Trabalho • 7 Days to Die")
    return embed


# ===================================================
# ==============  VIEW DE BOTÕES  ===================
# ===================================================

class PerguntaView(discord.ui.View):
    """
    View genérica: exibe botões "Sim" e "Não".
    - Se clicar em "Sim": envia o embed e apaga a pergunta; 1 min depois, apaga o embed.
    - Se clicar em "Não" ou se der timeout (30s), apaga a pergunta e não faz mais nada.
    """
    def __init__(self, embed: discord.Embed, timeout: float = 30.0, remover_msg_depois: float = 60.0):
        super().__init__(timeout=timeout)
        self.message = None               # Referência à mensagem de pergunta
        self.embed = embed                # Embed que será enviado se clicar em "Sim"
        self.remover_msg_depois = remover_msg_depois

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def botao_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        # Envia o embed no canal
        msg_embed = await interaction.followup.send(embed=self.embed)

        # Apaga a mensagem de pergunta (onde estão os botões)
        if self.message:
            try:
                await self.message.delete()
            except:
                pass

        # Aguarda X segundos e então apaga o embed
        await asyncio.sleep(self.remover_msg_depois)
        try:
            await msg_embed.delete()
        except:
            pass

        self.stop()

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def botao_nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Apenas remove a mensagem de pergunta
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()

    async def on_timeout(self):
        """Se ninguém clicar em nada após 'timeout' (30s), apaga a mensagem de pergunta."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.stop()


# ===================================================
# ========== COG PRINCIPAL (AJUDA COMPLETA) =========
# ===================================================

class AjudaCompletaCog(commands.Cog):
    """
    Cog que detecta keywords para:
    - COMANDOS DO SERVIDOR
    - ARMADURAS
    - VEÍCULOS
    - ESTAÇÕES DE TRABALHO (FORJA, FOGUEIRA, BANCADA, etc.)
    E, ao encontrar, pergunta se o usuário quer ver. Usa botões "Sim"/"Não".
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora bots (incluindo o próprio)
        if message.author.bot:
            return

        content_lower = message.content.lower()

        # 1) COMANDOS
        if any(k in content_lower for k in KEYWORDS_COMANDOS):
            embed_comandos = criar_embed_comandos()
            view = PerguntaView(embed_comandos, timeout=30.0, remover_msg_depois=60.0)
            msg = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de COMANDOS do servidor?",
                view=view
            )
            view.message = msg
            return

        # 2) ARMADURAS
        if any(k in content_lower for k in KEYWORDS_ARMADURAS):
            embed_armaduras = criar_embed_armaduras()
            view = PerguntaView(embed_armaduras, timeout=30.0, remover_msg_depois=60.0)
            msg = await message.channel.send(
                f"{message.author.mention}, deseja ver a lista de ARMADURAS e seus bônus?",
                view=view
            )
            view.message = msg
            return

        # 3) VEÍCULOS
        if any(k in content_lower for k in KEYWORDS_VEICULOS):
            embed_veiculos = criar_embed_veiculos()
            view = PerguntaView(embed_veiculos, timeout=30.0, remover_msg_depois=60.0)
            msg = await message.channel.send(
                f"{message.author.mention}, deseja ver as informações sobre VEÍCULOS?",
                view=view
            )
            view.message = msg
            return

        # 4) ESTAÇÕES DE TRABALHO
        if any(k in content_lower for k in KEYWORDS_ESTACOES):
            embed_estacoes = criar_embed_estacoes()
            view = PerguntaView(embed_estacoes, timeout=30.0, remover_msg_depois=60.0)
            msg = await message.channel.send(
                f"{message.author.mention}, deseja ver as ESTAÇÕES DE TRABALHO (forja, fogueira, etc.)?",
                view=view
            )
            view.message = msg
            return


async def setup(bot: commands.Bot):
    """
    Função de setup para carregar o Cog no bot.
    No seu main.py, faça:
       await bot.load_extension("ajuda_completa")
    (ajuste o caminho de acordo com sua estrutura).
    """
    await bot.add_cog(AjudaCompletaCog(bot))
