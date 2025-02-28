import os
import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
import random
from googletrans import Translator

# Intents
intents = discord.Intents.all()

# Cria o cliente do bot
bot = discord.Client(intents=intents)

# "tree" é o gerenciador de slash commands (Application Commands)
tree = app_commands.CommandTree(bot)

# Instancia o tradutor
translator = Translator()

# Lista de status para alternar periodicamente
STATUS_LIST = [
    "traduzindo",
    "mantando zumbi",
    "falando com willi",
    "nova era pve"
]

########################################
#         LOOP DE STATUS
########################################
@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

########################################
#       EVENTO ON_READY
########################################
@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    # Sincroniza os slash commands com o Discord
    try:
        synced = await tree.sync()
        print(f"Comandos de barra sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

    # Inicia a tarefa de mudança de status
    change_status.start()

########################################
#         FUNÇÃO DE TRADUÇÃO
########################################
def translate_text(text: str, dest: str) -> str:
    """
    Usa googletrans para traduzir o texto para o idioma 'dest' (pt, en, es, etc.)
    """
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro na tradução: {e}")
        return None

########################################
#       SLASH COMMAND /traduzir
########################################
@tree.command(name="traduzir", description="Inicia o processo de tradução via reações de idioma.")
async def slash_traduzir(interaction: discord.Interaction):
    """
    Esse comando não recebe texto diretamente, pois a escolha do idioma
    será feita por reações, e o texto será buscado pela resposta/ID de mensagem.
    """
    # Manda uma mensagem inicial explicando o que fazer
    await interaction.response.send_message(
        "Use este comando **respondendo** a uma mensagem que deseja traduzir, ou "
        "forneça o ID da mensagem com `$traduzir <ID>` no chat.\n\n"
        "**Vou enviar um prompt com bandeiras para escolher o idioma.**",
        ephemeral=True  # só o autor do comando vê essa mensagem
    )

    # Agora, enviamos no canal (público) um prompt de "chame o comando $traduzir"
    # ou, se preferir, você pode iniciar diretamente o fluxo de reações aqui
    # Mas, para simplificar, deixamos a lógica de reações no comando `$traduzir`
    # (você pode manter ou remover essa explicação adicional)

########################################
#       COMANDO CLÁSSICO $traduzir
########################################
# Mantemos o comando de texto para mostrar como integrar com slash commands
# Caso queira apenas slash commands, comente ou remova esse bloco.
discord_command_bot = commands.Bot(command_prefix="$", intents=intents)
# Reaproveitando a mesma instância do bot principal
discord_command_bot._connection = bot._connection  # "fusão" simples
bot_sub = discord_command_bot  # para ficar mais claro

@bot_sub.command(name="traduzir")
async def traduzir(ctx, message_id: str = None):
    target_message = None

    # Se o comando for usado em resposta a uma mensagem
    if ctx.message.reference:
        try:
            target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except Exception:
            await ctx.send("Não foi possível recuperar a mensagem referenciada.")
            return
    # Se o usuário fornecer um ID de mensagem
    elif message_id:
        try:
            target_message = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send("Não foi possível encontrar a mensagem com o ID fornecido.")
            return
    else:
        await ctx.send("Por favor, responda a mensagem que deseja traduzir ou forneça o ID da mensagem.")
        return

    # Envia mensagem de prompt com as opções de idioma (bandeiras)
    prompt = await ctx.send(
        "Escolha o idioma para tradução:\n"
        "🇧🇷 - Português\n"
        "🇺🇸 - Inglês\n"
        "🇪🇸 - Espanhol"
    )
    emojis = ["🇧🇷", "🇺🇸", "🇪🇸"]
    for emoji in emojis:
        await prompt.add_reaction(emoji)

    # Filtro para capturar somente a reação do autor na mensagem de prompt
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in emojis and reaction.message.id == prompt.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Tempo esgotado. Por favor, tente novamente.")
        return

    # Após reagir, apaga o prompt para não poluir o chat
    try:
        await prompt.delete()
    except Exception as e:
        print("Não foi possível apagar a mensagem de prompt:", e)

    # Mapeia a reação escolhida para o código do idioma
    if str(reaction.emoji) == "🇧🇷":
        target_language = "pt"
    elif str(reaction.emoji) == "🇺🇸":
        target_language = "en"
    elif str(reaction.emoji) == "🇪🇸":
        target_language = "es"
    else:
        target_language = "pt"

    # Envia mensagem temporária indicando que a tradução está em andamento
    msg = await ctx.send("Traduzindo...")

    try:
        translated_text = translate_text(target_message.content, target_language)
        if not translated_text:
            await msg.edit(content="Houve um erro ao tentar traduzir a mensagem.")
            return
        # Edita a mensagem para mostrar somente a tradução
        await msg.edit(content=f"**Tradução ({target_language}):** {translated_text}")
    except Exception as e:
        await msg.edit(content="Houve um erro ao tentar traduzir a mensagem. Tente novamente mais tarde.")
        print("Exceção durante tradução:", e)
        return

    # Adiciona emojis para feedback: "👌" (positivo) e "👎" (negativo)
    feedback_emojis = ["👌", "👎"]
    for emoji in feedback_emojis:
        try:
            await msg.add_reaction(emoji)
        except Exception as e:
            print("Erro ao adicionar reação de feedback:", e)

    # Filtro para capturar somente a reação do autor no feedback
    def feedback_check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in feedback_emojis and reaction.message.id == msg.id

    try:
        reaction_fb, _ = await bot.wait_for("reaction_add", timeout=30.0, check=feedback_check)
    except asyncio.TimeoutError:
        # Se o tempo esgotar, não altera a mensagem
        return

    # Adiciona o feedback à mensagem editando seu conteúdo
    if str(reaction_fb.emoji) == "👌":
        feedback = "\n\nFeedback: Joia, tradução aprovada!"
    elif str(reaction_fb.emoji) == "👎":
        feedback = "\n\nFeedback: Tradução não aprovada."
    else:
        feedback = ""
    try:
        await msg.edit(content=f"{msg.content}{feedback}")
    except Exception as e:
        print("Erro ao editar a mensagem com feedback:", e)

# Função principal que inicia o bot
async def main():
    # Inicia o "bot principal"
    asyncio.create_task(bot.start(os.getenv("TOKEN")))
    # Inicia o "bot de comandos" (compartilhando a conexão)
    # Observação: Essa forma de "mesclar" clients não é a mais comum,
    # mas é um truque para manter slash commands e comandos clássicos no mesmo script.
    # Alternativamente, você pode migrar tudo para slash commands ou tudo para commands Bot.
    await bot_sub.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
