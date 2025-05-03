# cogs/ranks_cog.py
import re, asyncio, discord
from typing import Optional, Tuple, Dict
from discord.ext import commands
from discord import app_commands

LIMIT_PER_CLAN = 6500
CHANNEL_ID = 1367957693809033267
CHECK_DELAY = 2

LINE_RE = re.compile(r"\s*(\d+)\s+(.+?)\s+([0-9]{1,3}(?:[.,][0-9]{3})*)\s*$")


def parse_line(line: str) -> Optional[Tuple[str, int]]:
    m = LINE_RE.match(line)
    if not m:
        return None
    guild = m.group(2).strip()
    blocks = int(m.group(3).replace(".", "").replace(",", ""))
    return guild, blocks


class RanksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.exceeded: Dict[str, int] = {}
        self.embed_message: Optional[discord.Message] = None

    # ---------- listeners ----------
    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        if m.author.bot and m.channel.id == CHANNEL_ID:
            await self._process(m.content, m.channel)

    @commands.Cog.listener()
    async def on_message_edit(self, _b, a):
        if a.author.bot and a.channel.id == CHANNEL_ID:
            await asyncio.sleep(CHECK_DELAY)
            await self._process(a.content, a.channel)

    # ---------- command (slash + prefix) ----------
    @app_commands.command(name="scanrank", description="Força leitura do último ranking")
    async def scanrank_slash(self, itx: discord.Interaction):
        await itx.response.defer(thinking=True, ephemeral=True)
        ch = self.bot.get_channel(CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            await itx.followup.send("Canal não encontrado.", ephemeral=True)
            return
        last = await ch.history(limit=1).flatten()
        if not last:
            await itx.followup.send("Nenhuma mensagem para ler.", ephemeral=True)
            return
        await self._process(last[0].content, ch)
        await itx.followup.send("Rank analisado.", ephemeral=True)

    @commands.command(name="scanrank", help="Força leitura do último ranking")
    async def scanrank_prefix(self, ctx: commands.Context):
        ch = self.bot.get_channel(CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            await ctx.send("Canal não encontrado."); return
        last = await ch.history(limit=1).flatten()
        if not last:
            await ctx.send("Nenhuma mensagem para ler."); return
        await self._process(last[0].content, ch)
        await ctx.message.add_reaction("✅")

    # ---------- core ----------
    async def _process(self, text: str, channel: discord.TextChannel):
        text = text.strip("`\n")
        current: Dict[str, int] = {}
        for line in filter(None, text.split("\n")):
            p = parse_line(line)
            if p:
                g, b = p
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
            if g not in current:
                del self.exceeded[g]
                changed = True

        if changed:
            await self._update_embed(channel)

    async def _update_embed(self, channel: discord.TextChannel):
        if not self.exceeded:
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

# ---------- setup ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(RanksCog(bot))
