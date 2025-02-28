import discord
from discord import app_commands
from discord.ext import commands
from googletrans import Translator

# ======================
# Tradutor
# ======================
translator = Translator()

def translate_text(text: str, dest: str) -> str:
    """
    Função simples para traduzir usando googletrans.
    Retorna a string traduzida ou None se ocorrer erro.
    """
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro ao traduzir: {e}")
        return None

# ======================
# Select Menu
# ======================
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
        # Quando o usuário escolher, capturamos a seleção
        self.view.selected_language = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class LanguageSelectView(discord.ui.View):
    """
    View que inclui o Select Menu de idiomas.
    """
    def __init__(self):
        super().__init__(timeout=30)
        self.selected_language = None
        self.add_item(LanguageSelect())

# ======================
# Cog principal
# ======================
class UtilityCog(commands.Cog):
    """Comandos de utilidade: /ping, /traduzir, etc."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Mostra o tempo de resposta do bot")
    async def ping(self, interaction: discord.Interaction):
        """
        Comando para verificar se o bot está responsivo.
        """
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latência: **{latency}ms**",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="traduzir",
        description="Traduza uma mensagem pelo ID ou responda a uma mensagem."
    )
    @app_commands.describe(
        mensagem="ID da mensagem (opcional). Se não informar, responda diretamente a uma mensagem."
    )
    async def traduzir(self, interaction: discord.Interaction, mensagem: str = None):
        """
        Traduz o conteúdo de uma mensagem existente no canal.
        Exemplo de uso: /traduzir mensagem:123456789012345678
        Ou responda a uma mensagem e use /traduzir sem parâmetros.
        """
        # Defer ephemeral para não poluir o chat
        await interaction.response.defer(thinking=True, ephemeral=True)

        channel = interaction.channel
        target_message = None

        # 1) Se o usuário informou um ID
        if mensagem:
            try:
                target_message = await channel.fetch_message(mensagem)
            except:
                embed = discord.Embed(
                    description="❌ **Não encontrei nenhuma mensagem com esse ID.**",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        else:
            # 2) Se não informou ID, tenta pegar a referência (resposta)
            ref = interaction.message.reference
            if ref:
                try:
                    target_message = await channel.fetch_message(ref.message_id)
                except:
                    pass

            if not target_message:
                embed = discord.Embed(
                    description="⚠️ **Você precisa informar o ID ou responder a uma mensagem!**",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        # 3) Pede ao usuário que escolha o idioma via Select Menu
        view = LanguageSelectView()
        embed_prompt = discord.Embed(
            title="🌎 Escolha o idioma para tradução",
            description="Selecione abaixo qual idioma deseja usar como destino.",
            color=discord.Color.blue()
        )
        prompt = await interaction.followup.send(embed=embed_prompt, view=view, ephemeral=True)

        # Espera até que o usuário escolha ou o tempo se esgote
        await view.wait()

        if not view.selected_language:
            embed_timeout = discord.Embed(
                description="⏳ **Tempo esgotado ou não houve seleção de idioma.**",
                color=discord.Color.orange()
            )
            await prompt.edit(embed=embed_timeout, view=None)
            return

        # 4) Faz a tradução
        lang = view.selected_language
        translated_text = translate_text(target_message.content, lang)

        if not translated_text:
            embed_error = discord.Embed(
                description="❌ **Ocorreu um erro ao traduzir. Tente novamente!**",
                color=discord.Color.red()
            )
            await prompt.edit(embed=embed_error, view=None)
            return

        # 5) Exibe o resultado em um embed
        embed_result = discord.Embed(
            title="Tradução",
            description=f"**Idioma:** `{lang}`\n\n{translated_text}",
            color=discord.Color.green()
        )
        await prompt.edit(embed=embed_result, view=None)

async def setup(bot):
    """Função que o discord.py chama para carregar esta cog."""
    await bot.add_cog(UtilityCog(bot))
