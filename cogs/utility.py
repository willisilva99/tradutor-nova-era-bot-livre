# cogs/utility_cog.py
import asyncio, datetime, discord
from discord.ext import commands
from discord import app_commands
from deep_translator import GoogleTranslator


# -------- tradução assíncrona ----------
async def translate_text(text: str, dest: str) -> str | None:
    loop = asyncio.get_running_loop()

    def _sync():
        return GoogleTranslator(source="auto", target=dest).translate(text)

    try:
        return await loop.run_in_executor(None, _sync)
    except Exception as e:
        print(f"[translate] erro: {e}")
        return None
# ---------------------------------------


# -------- idiomas & UI ------------------
_LANGS = {
    "🇧🇷": ("pt", "Português"),
    "🇺🇸": ("en", "Inglês"),
    "🇪🇸": ("es", "Espanhol"),
    "🇫🇷": ("fr", "Francês"),
    "🇵🇾": ("es", "Espanhol (PY)"),
    "🟢":  ("gn", "Guarani"),
}

class LanguageSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Escolha o idioma destino…",
            options=[
                discord.SelectOption(label=n, value=c, emoji=e)
                for e, (c, n) in _LANGS.items()
            ])

    async def callback(self, interaction: discord.Interaction):
        self.view.selected = self.values[0]
        await interaction.response.defer()
        self.view.stop()

class LanguageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.selected = None
        self.add_item(LanguageSelect())
# ----------------------------------------


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /traduzir ----------
    @app_commands.command(
        name="traduzir",
        description="Traduza texto, uma mensagem (ID) ou reply."
    )
    async def traduzir_slash(self, itx: discord.Interaction,
                             mensagem: str | None = None):
        await itx.response.defer(thinking=True)

        alvo = await self._resolver_alvo(itx.channel, mensagem, itx.message)
        if not alvo:
            await itx.followup.send(embed=self._e_alerta(
                "Forneça texto, ID ou responda a uma mensagem."))
            return

        view = LanguageSelectView()
        prompt = await itx.followup.send(embed=self._e_base(
            "🌎 Selecione o idioma destino"), view=view)

        await view.wait()
        lang = view.selected
        if not lang:
            await prompt.edit(embed=self._e_alerta("⏳ Tempo esgotado."), view=None)
            return

        traduzido = await translate_text(alvo, lang)
        if not traduzido:
            await prompt.edit(embed=self._e_alerta("❌ Erro na tradução."), view=None)
            return

        await prompt.edit(embed=self._e_result(lang, alvo, traduzido), view=None)

    # ---------- !traduzir ----------
    @commands.command(help="!traduzir [texto|ID]  ou responda a mensagem.")
    async def traduzir(self, ctx: commands.Context, *, arg: str | None = None):
        alvo = await self._resolver_alvo(ctx.channel, arg, ctx.message)
        if not alvo:
            await ctx.send(embed=self._e_alerta(
                "Envie `!traduzir texto`, `!traduzir ID` ou responda a uma mensagem."))
            return

        msg_menu = await ctx.send(embed=self._e_base(
            "🌎 Reaja para escolher idioma",
            "\n".join(f"{e} → {n}" for e, (_, n) in _LANGS.items())))
        for e in _LANGS: await msg_menu.add_reaction(e)

        def chk(r, u): return u == ctx.author and r.message.id == msg_menu.id and str(r.emoji) in _LANGS
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30, check=chk)
        except asyncio.TimeoutError:
            await msg_menu.edit(embed=self._e_alerta("⏳ Tempo esgotado.")); return
        await msg_menu.delete()

        lang = _LANGS[str(reaction.emoji)][0]
        status = await ctx.send(embed=self._e_base("🔄 Traduzindo…"))
        traduzido = await translate_text(alvo, lang)
        if not traduzido:
            await status.edit(embed=self._e_alerta("❌ Erro na tradução.")); return
        await status.edit(embed=self._e_result(lang, alvo, traduzido))

    # ---------- ping ----------
    @app_commands.command(name="ping", description="Mostra latência")
    async def ping_slash(self, itx: discord.Interaction):
        await itx.response.send_message(f"🏓 {round(self.bot.latency*1000)} ms")

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        await ctx.send(f"🏓 {round(self.bot.latency*1000)} ms")

    # ---------- Embeds util ----------
    def _e_base(self, title: str, desc: str | None = None, color=0xF44336):
        e = discord.Embed(title=title, description=desc, colour=color)
        e.set_footer(text="WL Designer • deep-translator")
        e.timestamp = datetime.datetime.utcnow()
        return e

    def _e_alerta(self, texto: str):
        return self._e_base("Aviso", texto, 0xFFC107)

    def _e_result(self, lang: str, original: str, traduzido: str):
        nome = next(n for _, (c, n) in _LANGS.items() if c == lang)
        e = self._e_base("✅ Tradução concluída", colour=0x4CAF50)
        e.add_field(name="Idioma destino", value=f"`{lang}` • {nome}", inline=False)
        e.add_field(name="Original", value=discord.utils.escape_markdown(original),
                    inline=False)
        e.add_field(name="Traduzido", value=traduzido, inline=False)
        return e

    # ---------- helpers ----------
    async def _resolver_alvo(self, canal, conteudo, ref_msg):
        if ref_msg and ref_msg.reference:
            try:
                msg = await canal.fetch_message(ref_msg.reference.message_id)
                return msg.content
            except: pass
        if conteudo and conteudo.isdigit():
            try:
                msg = await canal.fetch_message(conteudo)
                return msg.content
            except: pass
        return conteudo or None


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
