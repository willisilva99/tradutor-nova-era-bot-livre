import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
from googletrans import Translator

# ==============================================
# Configurações Iniciais
# ==============================================
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix="$", intents=intents)

translator = Translator()

STATUS_LIST = [
    "traduzindo",
    "matando zumbis",
    "falando com Willi",
    "nova era PvE"
]

# ==============================================
# Task: troca de status periodicamente
# ==============================================
@tasks.loop(minutes=5)
async def change_status():
    status = random.choice(STATUS_LIST)
    await bot.change_presence(activity=discord.Game(name=status))
    print(f"Status atualizado para: {status}")

# ==============================================
# Evento on_ready: dispara quando o bot conecta
# ==============================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

    # Define um status inicial
    activity = discord.Game(name="sesh.fyi | /help")
    await bot.change_presence(activity=activity)

    # Sincroniza slash commands (apenas uma vez)
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos sincronizados com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

    # Inicia o loop de troca de status, se ainda não estiver rodando
    if not change_status.is_running():
        change_status.start()

# ==============================================
# Comando /sync (força sincronização manual)
# ==============================================
@bot.tree.command(name="sync", description="Força a sincronização dos comandos manualmente")
async def sync_commands(interaction: discord.Interaction):
    try:
        synced = await bot.tree.sync()
        await interaction.response.send_message(f"🔄 **{len(synced)} comandos sincronizados manualmente!**", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ **Erro ao sincronizar:** {e}", ephemeral=True)

# ==============================================
# Função de tradução com googletrans
# ==============================================
def translate_text(text: str, dest: str) -> str:
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro na tradução: {e}")
        return None

# ==============================================
# Classe de Select Menu para seleção de idioma
# ==============================================
class LanguageSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Português", value="pt", emoji="🇧🇷"),
            discord.SelectOption(label="Inglês", value="en", emoji="🇺🇸"),
            discord.SelectOption(label="Espanhol", value="es", emoji="🇪🇸")
        ]
        super().__init__(
            placeholder="Escolha o idioma de destino...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_language = self.values[0]
        # Assim que o usuário selecionar, encerra a view
        await interaction.response.defer()
        self.view.stop()

class LanguageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.selected_language = None
        self.add_item(LanguageSelect())

# ==============================================
# Slash Command /traduzir
# ==============================================
@bot.tree.command(name="traduzir", description="Traduza uma mensagem pelo ID ou responda a uma.")
@app_commands.describe(
    mensagem="ID da mensagem (opcional). Se não informar, responda diretamente a uma mensagem."
)
async def slash_traduzir(interaction: discord.Interaction, mensagem: str = None):
    """Traduza o conteúdo de uma mensagem existente no canal."""
    await interaction.response.defer(thinking=True, ephemeral=True)
    channel = interaction.channel
    target_message = None

    # 1) Se informaram um ID
    if mensagem:
        try:
            target_message = await channel.fetch_message(mensagem)
        except:
            await interaction.followup.send("❌ **Não encontrei nenhuma mensagem com esse ID.**", ephemeral=True)
            return
    # 2) Se não houve ID, tenta pegar a referência (resposta)
    else:
        ref = interaction.message.reference
        if ref:
            try:
                target_message = await channel.fetch_message(ref.message_id)
            except:
                pass
        if not target_message:
            await interaction.followup.send("⚠️ **Você precisa informar o ID ou responder a uma mensagem!**", ephemeral=True)
            return

    # Pergunta o idioma via Select Menu
    view = LanguageSelectView()
    prompt = await interaction.followup.send(
        "🌎 **Selecione o idioma para tradução:**",
        view=view,
        ephemeral=True
    )

    # Aguarda até que a pessoa escolha (ou expire)
    await view.wait()

    if not view.selected_language:
        await prompt.edit(content="⏳ **Tempo esgotado ou não foi selecionado nenhum idioma.**", view=None)
        return

    # Idioma escolhido
    target_language = view.selected_language

    # Traduz
    translated_text = translate_text(target_message.content, target_language)
    if not translated_text:
        await prompt.edit(content="❌ **Ocorreu um erro ao traduzir. Tente novamente!**", view=None)
        return

    # Mostra resultado
    await prompt.edit(
        content=(
            f"✅ **Tradução para `{target_language}`:**\n"
            f"{translated_text}"
        ),
        view=None
    )

# ==============================================
# Slash Command /ping
# ==============================================
@bot.tree.command(name="ping", description="Mostra o tempo de resposta do bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latência: `{latency}ms`")

# ==============================================
# Slash Command /clear
# Verifica permissão: manage_messages
# ==============================================
@bot.tree.command(name="clear", description="Limpa mensagens do chat (máx: 3000)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Quantidade de mensagens a deletar (1-3000)")
async def clear(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 3000:
        await interaction.response.send_message("⚠️ **Escolha um número entre 1 e 3000.**", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 **{len(deleted)} mensagens apagadas!**", ephemeral=True)

# ==============================================
# Tratamento de erro específico para /clear
# ==============================================
@clear.error
async def clear_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ **Você não tem permissão para apagar mensagens!**",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(f"❌ **Erro:** {error}", ephemeral=True)

# ==============================================
# Inicia o bot
# ==============================================
async def main():
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
