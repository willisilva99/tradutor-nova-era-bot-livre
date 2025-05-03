import re
import asyncio
import discord
from discord.ext import commands
from typing import Optional, Tuple

# ----------------- CONFIG -----------------
LIMIT_PER_CLAN = 6500                  # novo limite
RANK_ANNOUNCE_CHANNEL_ID = 1367957693809033267  # mesmo canal para ler e avisar
CHECK_DELAY = 2                        # segundos para reprocessar edições
# ------------------------------------------

def parse_line(line: str) -> Optional[Tuple[int, str, int]]:
    """Extrai (posição, guilda, blocos) de uma linha de ranking."""
    m = re.match(r"\s*(\d+)\s+(.+?)\s+(\d+)\s*$", line)
    if not m:
        return None
    pos = int(m.group(1))
    name = m.group(2).strip()
    blocks = int(m.group(3))
    return pos, name, blocks

class RanksCog(commands.Cog):
    """Monitora mensagens de ranking de blocos e avisa quando algum clã ultrapassa o limite."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.already_warned: dict[str, int] = {}

    # --------------- EVENTOS ---------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot and message.channel.id == RANK_ANNOUNCE_CHANNEL_ID:
            await self._process_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, _before: discord.Message, after: discord.Message):
        if after.author.bot and after.channel.id == RANK_ANNOUNCE_CHANNEL_ID:
            await asyncio.sleep(CHECK_DELAY)
            await self._process_message(after)

    # --------------- LÓGICA ---------------
    async def _process_message(self, message: discord.Message):
        lines = message.content.split("\n")
        exceeded: list[Tuple[str, int, int]] = []

        for line in lines:
            data = parse_line(line)
            if not data:
                continue
            _pos, guild, blocks = data
            if blocks > LIMIT_PER_CLAN:
                over = blocks - LIMIT_PER_CLAN
                prev = self.already_warned.get(guild)
                if prev is None or blocks > prev:
                    exceeded.append((guild, blocks, over))
                    self.already_warned[guild] = blocks
            else:
                self.already_warned.pop(guild, None)

        if exceeded:
            await self._announce(message.channel, exceeded)

    async def _announce(self, channel: discord.TextChannel, items: list[Tuple[str, int, int]]):
        embed = discord.Embed(
            title="🚨 Clãs acima do limite de blocos!",
            colour=0xE53935,
            description=f"Limite configurado: **{LIMIT_PER_CLAN:,}** blocos"
        )
        for guild, blocks, over in items:
            embed.add_field(
                name=guild,
                value=f"Total: **{blocks:,}**\nExcedente: **{over:,}** 🔴",
                inline=False
            )
        embed.set_footer(text="Anarquia Z – Monitor de Estruturas")
        await channel.send(embed=embed)

# --------------- SETUP ---------------
async def setup(bot: commands.Bot):
    await bot.add_cog(RanksCog(bot))
