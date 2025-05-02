import asyncio, discord
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

    # ------ /traduzir ------
    @app_commands.command(name="traduzir",
        description="Traduza uma mensagem pelo ID ou respondendo à mensagem.")
    @app_commands.describe(mensagem="ID da mensagem (opcional)")
    async def traduzir_slash(self, itx: discord.Interaction,
                             mensagem: str | None = None):
        await itx.response.defer(thinking=True, ephemeral=True)
        alvo = await self._pegar_mensagem(itx.channel, mensagem, itx.message)
        if not alvo:
            await itx.followup.send("⚠️ Informe o ID ou responda a uma mensagem!",
                                    ephemeral=True); return

        view = LanguageSelectView()
        prompt = await itx.followup.send(
            embed=discord.Embed(title="🌎 Escolha o idioma destino",
                                color=discord.Color.blue()),
            view=view, ephemeral=True)

        await view.wait()
        lang = view.selected
        if not lang:
            await prompt.edit(content="⏳ Tempo esgotado.", embed=None, view=None)
            return

        traduzido = await translate_text(alvo.content, lang)
        if not traduzido:
            await prompt.edit(content="❌ Erro na tradução.", embed=None, view=None)
            return

        await prompt.edit(embed=discord.Embed(
            title="Tradução",
            description=f"**Idioma:** `{lang}`\n\n{traduzido}",
            color=discord.Color.green()),
            view=None)

    # ------ !traduzir ------
    @commands.command(name="traduzir",
                      help="Traduza via prefixo (!traduzir [ID] ou reply).")
    async def traduzir_prefix(self, ctx: commands.Context,
                              mensagem_id: str | None = None):
        alvo = await self._pegar_mensagem(ctx.channel, mensagem_id, ctx.message)
        if not alvo:
            await ctx.send("⚠️ Informe o ID ou responda a uma mensagem!")
            return

        langs = {"🇧🇷": "pt", "🇺🇸": "en", "🇪🇸": "es"}
        embed = await ctx.send(embed=discord.Embed(
            title="🌎 Reaja para escolher idioma",
            description="\n".join(f"{e} → {c}" for e, c in langs.items()),
            color=discord.Color.blue()))
        for e in langs: await embed.add_reaction(e)

        def chk(r, u): return (u == ctx.author and str(r.emoji) in langs
                               and r.message.id == embed.id)
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30, check=chk)
        except asyncio.TimeoutError:
            await ctx.send("⏳ Tempo esgotado."); return
        await embed.delete()

        lang = langs[str(reaction.emoji)]
        msg = await ctx.send("🔄 Traduzindo…")
        traduzido = await translate_text(alvo.content, lang)
        if not traduzido:
            await msg.edit(content="❌ Erro na tradução."); return
        await msg.edit(content=f"✅ **({lang})** {traduzido}")

    # ------ ping ------
    @app_commands.command(name="ping", description="Latência do bot")
    async def ping_slash(self, itx: discord.Interaction):
        await itx.response.send_message(f"🏓 {round(self.bot.latency*1000)} ms")

    @commands.command(name="ping", help="Latência do bot")
    async def ping_prefix(self, ctx: commands.Context):
        await ctx.send(f"🏓 {round(self.bot.latency*1000)} ms")

    # ------ helpers ------
    async def _pegar_mensagem(self, canal, msg_id, referencia):
        if msg_id:
            try: return await canal.fetch_message(msg_id)
            except: return None
        if referencia and referencia.message_id:
            try: return await canal.fetch_message(referencia.message_id)
            except: pass
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
