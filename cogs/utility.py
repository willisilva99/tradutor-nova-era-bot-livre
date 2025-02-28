import discord
from discord.ext import commands
from discord import app_commands
from googletrans import Translator
import asyncio

translator = Translator()

def translate_text(text: str, dest: str) -> str:
    """Envia texto para tradução usando googletrans."""
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        print(f"Erro ao traduzir: {e}")
        return None

# ---------------------------
# SELECT MENU (Slash Command)
# ---------------------------
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
        await interaction.response.defer()
        self.view.stop()

class LanguageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.selected_language = None
        self.add_item(LanguageSelect())

# ---------------------------
# COG de Utilidades
# ---------------------------
class UtilityCog(commands.Cog):
    """Comandos de utilidade: /traduzir (slash), $traduzir (prefix) etc."""

    def __init__(self, bot):
        self.bot = bot

    # =================================
    # 1) Slash Command /traduzir
    # =================================
    @app_commands.command(
        name="traduzir",
        description="Traduza uma mensagem pelo ID ou responda a uma mensagem."
    )
    @app_commands.describe(
        mensagem="ID da mensagem (opcional). Se não informar, responda diretamente a uma mensagem."
    )
    async def traduzir_slash(self, interaction: discord.Interaction, mensagem: str = None):
        """Slash Command para traduzir mensagem."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        channel = interaction.channel
        target_message = None

        # 1) Se passou ID, tenta buscar
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
            # 2) Senão, tenta referência
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

        # 3) Select Menu de idiomas
        view = LanguageSelectView()
        embed_prompt = discord.Embed(
            title="🌎 Escolha o idioma para tradução",
            description="Selecione abaixo qual idioma deseja usar como destino.",
            color=discord.Color.blue()
        )
        prompt = await interaction.followup.send(embed=embed_prompt, view=view, ephemeral=True)

        # Espera até que o usuário selecione ou o tempo acabe
        await view.wait()

        if not view.selected_language:
            embed_timeout = discord.Embed(
                description="⏳ **Tempo esgotado ou não houve seleção de idioma.**",
                color=discord.Color.orange()
            )
            await prompt.edit(embed=embed_timeout, view=None)
            return

        # 4) Traduz
        lang = view.selected_language
        translated_text = translate_text(target_message.content, lang)

        if not translated_text:
            embed_error = discord.Embed(
                description="❌ **Ocorreu um erro ao traduzir. Tente novamente!**",
                color=discord.Color.red()
            )
            await prompt.edit(embed=embed_error, view=None)
            return

        embed_result = discord.Embed(
            title="Tradução",
            description=f"**Idioma:** `{lang}`\n\n{translated_text}",
            color=discord.Color.green()
        )
        await prompt.edit(embed=embed_result, view=None)

    # =================================
    # 2) Comando com Prefixo $traduzir
    # =================================
    @commands.command(name="traduzir", help="Traduza uma mensagem via prefixo. Use: $traduzir [message_id ou responda]")
    async def traduzir_prefix(self, ctx: commands.Context, message_id: str = None):
        """
        Comando prefixado ($traduzir).
        Exemplo:
        - $traduzir 1234567890 (ID de uma mensagem)
        - Em resposta a uma mensagem: $traduzir
        """
        channel = ctx.channel
        target_message = None

        # 1) Se o usuário informou um ID
        if message_id:
            try:
                target_message = await channel.fetch_message(message_id)
            except:
                await ctx.send(embed=discord.Embed(
                    description="❌ **Não encontrei nenhuma mensagem com esse ID.**",
                    color=discord.Color.red()
                ))
                return
        else:
            # 2) Tenta pegar a referência (caso o usuário tenha dado reply em alguma mensagem)
            if ctx.message.reference:
                try:
                    ref_id = ctx.message.reference.message_id
                    target_message = await channel.fetch_message(ref_id)
                except:
                    pass

            if not target_message:
                await ctx.send(embed=discord.Embed(
                    description="⚠️ **Informe um ID ou responda a uma mensagem!**",
                    color=discord.Color.yellow()
                ))
                return

        # 3) Para o comando prefixado, vamos usar REAÇÕES (🇧🇷, 🇺🇸, 🇪🇸) para escolher idioma
        embed_prompt = discord.Embed(
            title="🌎 Selecione o idioma para tradução",
            description="Reaja com:\n🇧🇷 para Português\n🇺🇸 para Inglês\n🇪🇸 para Espanhol",
            color=discord.Color.blue()
        )
        prompt = await ctx.send(embed=embed_prompt)

        emojis = ["🇧🇷", "🇺🇸", "🇪🇸"]
        for e in emojis:
            await prompt.add_reaction(e)

        def check(reaction, user):
            return (
                user == ctx.author 
                and str(reaction.emoji) in emojis 
                and reaction.message.id == prompt.id
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(
                description="⏳ **Tempo esgotado!**",
                color=discord.Color.orange()
            ))
            return

        try:
            await prompt.delete()
        except:
            pass

        # Dicionário de idiomas
        langs = {
            "🇧🇷": "pt",
            "🇺🇸": "en",
            "🇪🇸": "es"
        }

        lang = langs.get(str(reaction.emoji), "pt")

        # 4) Traduz
        msg_status = await ctx.send("🔄 **Traduzindo...**")
        translated_text = translate_text(target_message.content, lang)

        if not translated_text:
            await msg_status.edit(content="❌ **Ocorreu um erro ao traduzir.**")
            return

        await msg_status.edit(content=f"✅ **Tradução (`{lang}`):** {translated_text}")

    # --------------------------------
    # Exemplo de /ping e $ping
    # --------------------------------
    # Slash Command /ping
    @app_commands.command(name="ping", description="Mostra o tempo de resposta do bot")
    async def ping_slash(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latência: **{latency}ms**",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    # Prefix Command $ping
    @commands.command(name="ping", help="Mostra o tempo de resposta do bot (prefixado)")
    async def ping_prefix(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latência: **{latency}ms**",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

# ---------------------------
# Config de carregamento
# ---------------------------
async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
