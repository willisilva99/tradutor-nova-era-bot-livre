# cogs/utility_cog.py
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from deep_translator import GoogleTranslator


# ---------- tradução assíncrona ----------
async def translate_text(text: str, dest: str) -> str | None:
    loop = asyncio.get_running_loop()

    def _sync():
        return GoogleTranslator(source="auto", target=dest).translate(text)

    try:
        return await loop.run_in_executor(None, _sync)
    except Exception as e:
        print(f"[translate] erro: {e}")
        return None
# -----------------------------------------


# ---------- UI (Select / Reactions) ------
class LanguageSelect(discord.ui.Select):
    OPTIONS = [
        discord.SelectOption(label="Português", value="pt", emoji="🇧🇷"),
        discord.SelectOption(label="Inglês",     value="en", emoji="🇺🇸"),
        discord.SelectOption(label="Espanhol",   value="es", emoji="🇪🇸")
    ]
    def __init__(self):
        super().__init__(placeholder="Escolha o idioma…", min_values=1,
                         max_values=1, options=self.OPTIONS)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class LanguageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.selected: str | None = None
        self.add_item(LanguageSelect())
# -----------------------------------------


class UtilityCog(commands.Cog):
    """/traduzir · !traduzir · /ping · !ping"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /traduzir ----------
    @app_commands.command(
        name="traduzir",
        description="Traduza uma mensagem (ID, reply) ou texto direto."
    )
    @app_commands.describe(mensagem="ID da mensagem ou texto a traduzir")
    async def traduzir_slash(
        self,
        itx: discord.Interaction,
        mensagem: str | None = None
    ):
        await itx.response.defer(thinking=True)  # público
        alvo = await self._resolver_alvo(itx.channel, mensagem, itx.message)

        if not alvo:
            await itx.followup.send(
                "⚠️ Forneça texto, ID ou responda a uma mensagem."
            )
            return

        view = LanguageSelectView()
        prompt = await itx.followup.send(
            embed=discord.Embed(
                title="🌎 Escolha o idioma destino",
                color=discord.Color.blue()
            ),
            view=view
        )

        await view.wait()
        lang = view.selected
        if not lang:
            await prompt.edit(content="⏳ Tempo esgotado.", embed=None, view=None)
            return

        traduzido = await translate_text(alvo, lang)
        if not traduzido:
            await prompt.edit(content="❌ Erro na tradução.", embed=None, view=None)
            return

        await prompt.edit(
            embed=discord.Embed(
                title="Tradução",
                description=f"**Idioma:** `{lang}`\n\n{traduzido}",
                color=discord.Color.green()
            ),
            view=None
        )

    # ---------- !traduzir ----------
    @commands.command(
        name="traduzir",
        help="!traduzir [texto ou ID]  |  responda a mensagem para traduzir."
    )
    async def traduzir_prefix(self, ctx: commands.Context, *, arg: str | None = None):
        alvo = await self._resolver_alvo(ctx.channel, arg, ctx.message)

        if not alvo:
            await ctx.send(
                "⚠️ Envie `!traduzir texto`, `!traduzir <ID>` ou responda a uma mensagem."
            )
            return

        langs = {"🇧🇷": "pt", "🇺🇸": "en", "🇪🇸": "es"}
        msg_menu = await ctx.send(
            embed=discord.Embed(
                title="🌎 Reaja para escolher idioma",
                description="\n".join(f"{e} → {c}" for e, c in langs.items()),
                color=discord.Color.blue()
            )
        )
        for e in langs: await msg_menu.add_reaction(e)

        def chk(r, u): return (
            u == ctx.author and str(r.emoji) in langs and r.message.id == msg_menu.id
        )
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30, check=chk)
        except asyncio.TimeoutError:
            await ctx.send("⏳ Tempo esgotado."); return
        await msg_menu.delete()

        lang = langs[str(reaction.emoji)]
        status = await ctx.send("🔄 Traduzindo…")
        traduzido = await translate_text(alvo, lang)
        if not traduzido:
            await status.edit(content="❌ Erro na tradução."); return
        await status.edit(content=f"✅ **({lang})** {traduzido}")

    # ---------- ping ----------
    @app_commands.command(name="ping", description="Latência do bot")
    async def ping_slash(self, itx: discord.Interaction):
        await itx.response.send_message(f"🏓 {round(self.bot.latency*1000)} ms")

    @commands.command(name="ping", help="Latência do bot")
    async def ping_prefix(self, ctx: commands.Context):
        await ctx.send(f"🏓 {round(self.bot.latency*1000)} ms")

    # ---------- helpers ----------
    async def _resolver_alvo(self, canal, conteudo, ref_msg):
        """Retorna texto para traduzir."""
        # se reply
        if ref_msg and ref_msg.reference and ref_msg.reference.message_id:
            try:
                msg = await canal.fetch_message(ref_msg.reference.message_id)
                return msg.content
            except: pass
        # se ID numérico
        if conteudo and conteudo.isdigit():
            try:
                msg = await canal.fetch_message(conteudo)
                return msg.content
            except: pass
        # texto direto
        return conteudo if conteudo else None


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
