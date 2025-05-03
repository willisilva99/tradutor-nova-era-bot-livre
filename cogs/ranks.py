# cogs/ranks_cog.py
import re, asyncio, functools, discord
from typing import Optional, Tuple, Dict
from discord.ext import commands
from discord import app_commands

# ---------- CONFIG ----------
LIMIT_PER_CLAN = 6500
CHANNEL_ID = 1367957693809033267          # canal onde o ranking aparece e onde o aviso ficará
CHECK_DELAY = 2                           # espera após edições
# -----------------------------

LINE_RE = re.compile(r"\s*(\d+)\s+(.+?)\s+([0-9]{1,3}(?:[.,][0-9]{3})*)\s*$")


def parse_line(line: str) -> Optional[Tuple[str, int]]:
    """Retorna (guilda, blocos) ou None se a linha não bater."""
    m = LINE_RE.match(line)
    if not m:
        return None
    guild = m.group(2).strip()
    blocks = int(m.group(3).replace(".", "").replace(",", ""))
    return guild, blocks


class RanksCog(commands.Cog):
    """Mantém um único embed de alerta, atualizando quando o ranking mudar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.exceeded: Dict[str, int] = {}          # guild -> blocos atuais
        self.embed_message: Optional[discord.Message] = None

    # ---------- LISTENERS ----------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot and msg.channel.id == CHANNEL_ID:
            await self._process(msg.content, msg.channel)

    @commands.Cog.listener()
    async def on_message_edit(self, _b: discord.Message, after: discord.Message):
        if after.author.bot and after.channel.id == CHANNEL_ID:
            await asyncio.sleep(CHECK_DELAY)
            await self._process(after.content, after.channel)

    # ---------- COMMANDS ----------
    @app_commands.command(
        name="scanrank",
        description="Analisa o ranking; passe o ID da mensagem opcionalmente."
    )
    @app_commands.describe(msg_id="ID da mensagem com o ranking")
    async def scanrank_slash(self, itx: discord.Interaction, msg_id: str | None = None):
        await itx.response.defer(thinking=True, ephemeral=True)
        ch = self._get_channel(itx)
        if not ch:
            await itx.followup.send("Canal não encontrado.", ephemeral=True)
            return
        ok = await self._manual_scan(ch, msg_id)
        await itx.followup.send(
            "Ranking processado." if ok else "Ranking não encontrado.", ephemeral=True
        )

    @commands.command(name="scanrank", help="Analisa o ranking; opcionalmente passe o ID.")
    async def scanrank_prefix(self, ctx: commands.Context, msg_id: str | None = None):
        ch = self._get_channel(ctx)
        if not ch:
            await ctx.send("Canal não encontrado."); return
        ok = await self._manual_scan(ch, msg_id)
        if ok:
            await ctx.message.add_reaction("✅")
        else:
            await ctx.send("Ranking não encontrado.")

    # ---------- CORE ----------
    async def _manual_scan(self, ch: discord.TextChannel, msg_id: str | None) -> bool:
        """Retorna True se achou ranking e processou."""
        if msg_id and msg_id.isdigit():
            try:
                msg = await ch.fetch_message(int(msg_id))
                await self._process(msg.content, ch)
                return True
            except discord.NotFound:
                return False

        async for msg in ch.history(limit=50):
            if "Guilda" in msg.content and "Estruturas" in msg.content:
                await self._process(msg.content, ch)
                return True
        return False

    async def _process(self, text: str, channel: discord.TextChannel):
        text = text.strip("`\n")                      # remove ``` se presente
        current: Dict[str, int] = {}
        for line in filter(None, text.split("\n")):
            parsed = parse_line(line)
            if parsed:
                g, b = parsed
                current[g] = b

        changed = False
        for g, b in current.items():
            if b > LIMIT_PER_CLAN:
                if self.exceeded.get(g) != b:
                    self.exceeded[g] = b
                    changed = True
            else:
                if g in self.exceeded:
                    del self.exceeded[g]
                    changed = True

        for g in list(self.exceeded):
            if g not in current:                      # saiu do ranking
                del self.exceeded[g]
                changed = True

        if changed:
            await self._update_embed(channel)

    async def _update_embed(self, channel: discord.TextChannel):
        if not self.exceeded:                         # ninguém acima -> remove embed
            if self.embed_message:
                try:
                    await self.embed_message.delete()
                except discord.NotFound:
                    pass
                self.embed_message = None
            return

        emb = discord.Embed(
            title="🚨 Clãs acima do limite de blocos!",
            colour=0xE53935,
            description=f"Limite: **{LIMIT_PER_CLAN:,}** blocos",
        )
        for g, b in sorted(self.exceeded.items(), key=lambda x: (-x[1], x[0])):
            emb.add_field(
                name=g,
                value=f"Total: **{b:,}**\nExcesso: **{b - LIMIT_PER_CLAN:,}** 🔴",
                inline=False,
            )
        emb.set_footer(text="Anarquia Z • Monitor")

        if self.embed_message:
            try:
                await self.embed_message.edit(embed=emb)
            except discord.NotFound:
                self.embed_message = await channel.send(embed=emb)
        else:
            self.embed_message = await channel.send(embed=emb)

    # ---------- helpers ----------
    def _get_channel(self, ctx_or_itx) -> Optional[discord.TextChannel]:
        ch = self.bot.get_channel(CHANNEL_ID)
        return ch if isinstance(ch, discord.TextChannel) else None


async def setup(bot: commands.Bot):
    await bot.add_cog(RanksCog(bot))
