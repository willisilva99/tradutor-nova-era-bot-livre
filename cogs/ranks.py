import re, asyncio, discord
from typing import Optional, Tuple, Dict
from discord.ext import commands

LIMIT_PER_CLAN = 6500                      # limite de blocos
CHANNEL_ID = 1367957693809033267           # canal do ranking / aviso
CHECK_DELAY = 2                            # espera após edição

LINE_RE = re.compile(r"\s*(\d+)\s+(.+?)\s+([0-9]{1,3}(?:[.,][0-9]{3})*)\s*$")


def parse_line(line: str) -> Optional[Tuple[str, int]]:
    m = LINE_RE.match(line)
    if not m:
        return None
    guild = m.group(2).strip()
    blocks = int(m.group(3).replace(".", "").replace(",", ""))
    return guild, blocks


class RanksCog(commands.Cog):
    """Mantém um único embed de alerta, editando conforme os clãs excedem/retornam."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.exceeded: Dict[str, int] = {}      # guild -> blocos atuais
        self.embed_message: Optional[discord.Message] = None

    # -------- EVENTS --------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot and msg.channel.id == CHANNEL_ID:
            await self._process(msg)

    @commands.Cog.listener()
    async def on_message_edit(self, _b: discord.Message, a: discord.Message):
        if a.author.bot and a.channel.id == CHANNEL_ID:
            await asyncio.sleep(CHECK_DELAY)
            await self._process(a)

    # -------- CORE --------
    async def _process(self, msg: discord.Message):
        text = msg.content.strip("`\n")
        current: Dict[str, int] = {}
        for line in filter(None, text.split("\n")):
            parsed = parse_line(line)
            if parsed:
                g, b = parsed
                current[g] = b

        changed = False
        # detecta novos excedentes
        for g, b in current.items():
            if b > LIMIT_PER_CLAN:
                if self.exceeded.get(g) != b:
                    self.exceeded[g] = b
                    changed = True
            else:
                if g in self.exceeded:
                    del self.exceeded[g]
                    changed = True
        # remove clãs que saíram do ranking
        for g in list(self.exceeded):
            if g not in current:
                del self.exceeded[g]
                changed = True

        if changed:
            await self._update_embed(msg.channel)

    async def _update_embed(self, channel: discord.TextChannel):
        if not self.exceeded:
            if self.embed_message:
                try:
                    await self.embed_message.delete()
                except discord.NotFound:
                    pass
                self.embed_message = None
            return

        embed = discord.Embed(
            title="🚨 Clãs acima do limite de blocos!",
            colour=0xE53935,
            description=f"Limite: **{LIMIT_PER_CLAN:,}** blocos"
        )
        for g, b in sorted(self.exceeded.items(), key=lambda x: (-x[1], x[0])):
            over = b - LIMIT_PER_CLAN
            embed.add_field(name=g, value=f"Total: **{b:,}**\nExcedente: **{over:,}** 🔴", inline=False)
        embed.set_footer(text="Anarquia Z • Monitor")

        if self.embed_message:
            try:
                await self.embed_message.edit(embed=embed)
            except discord.NotFound:
                self.embed_message = await channel.send(embed=embed)
        else:
            self.embed_message = await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RanksCog(bot))
