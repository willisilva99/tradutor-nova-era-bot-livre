# cogs/profanity.py
import re
import os
import json
import logging
import discord
from discord.ext import commands
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ProfanityCog(commands.Cog):
    """
    Remove mensagens com palavrões, avisa com embed estilizado
    e bane automaticamente após 10 avisos.
    """
    STATE_FILE = "profanity_state.json"
    DEFAULT_LIMIT = 10  # avisos até ban

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        blocked = [
            "porra","caralho","merda","puta","cacete","fodase","foda-se",
            "filhodaputa","filho da puta","vai se foder","vai te catar",
            "viado","bicha","traveco","tchola","macaco","negro de merda",
            "crioulada","sua mãe","sua avó","seu pai","seu irmão",
            "idiota","burro","retardado","imbecil","otário"
        ]
        self.patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in blocked]
        self.warns = {}  # { guild_id: { user_id: count } }
        self.load_state()

    def cog_unload(self):
        self.save_state()

    def load_state(self):
        if os.path.isfile(self.STATE_FILE):
            with open(self.STATE_FILE, "r", encoding="utf-8") as f:
                self.warns = json.load(f)
        else:
            self.warns = {}

    def save_state(self):
        with open(self.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.warns, f, indent=2, ensure_ascii=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignora bots, DMs e administradores
        if message.author.bot or not message.guild:
            return await self.bot.process_commands(message)
        if message.author.guild_permissions.administrator:
            return await self.bot.process_commands(message)

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        for patt in self.patterns:
            m = patt.search(message.content)
            if not m:
                continue

            bad = m.group(0)
            try:
                await message.delete()
            except discord.Forbidden:
                return

            # contabiliza aviso
            guild_warns = self.warns.setdefault(guild_id, {})
            count = guild_warns.get(user_id, 0) + 1
            guild_warns[user_id] = count
            self.save_state()

            # embed de aviso
            warn_embed = discord.Embed(
                title=f"⚠️ {message.author.display_name}, atenção!",
                description=(
                    f"{message.author.mention}, sua mensagem continha **`{bad}`**, o que é proibido aqui.\n\n"
                    f"🔢 **Avisos:** {count}/{self.DEFAULT_LIMIT}\n"
                    f"📌 Você pode ser banido ao atingir {self.DEFAULT_LIMIT} avisos!\n"
                    f"📖 Leia as regras do servidor."
                ),
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            warn_embed.set_thumbnail(url=message.author.display_avatar.url)
            warn_embed.set_footer(text=f"{message.guild.name}")
            await message.channel.send(embed=warn_embed, delete_after=120)

            # ban automático
            if count >= self.DEFAULT_LIMIT:
                try:
                    await message.guild.ban(message.author, reason="Limite de xingamentos atingido")
                except discord.Forbidden:
                    return

                ban_embed = discord.Embed(
                    title=f"🔨 {message.author.display_name} banido!",
                    description=(
                        f"{message.author.mention} excedeu o limite de avisos.\n\n"
                        f"🆔 **ID:** `{user_id}`\n"
                        f"⚠️ **Avisos:** {count}/{self.DEFAULT_LIMIT}\n"
                        f"🔒 Ban aplicado automaticamente."
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                ban_embed.set_thumbnail(url=message.author.display_avatar.url)
                ban_embed.set_footer(text=f"{message.guild.name}")
                await message.channel.send(embed=ban_embed, delete_after=120)

                # reset contador
                guild_warns.pop(user_id, None)
                self.save_state()

            return

        await self.bot.process_commands(message)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
