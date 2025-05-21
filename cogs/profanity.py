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
    Remove mensagens com palavrões e avisa com um embed padronizado.
    """
    STATE_FILE = "profanity_state.json"
    DEFAULT_LIMIT = 5

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Palavras proibidas
        blocked = [
            "porra","caralho","merda","puta","cacete","fodase","foda-se",
            "filhodaputa","filho da puta","vai se foder","vai te catar",
            "viado","bicha","traveco","tchola","macaco","negro de merda",
            "crioulada","sua mãe","sua avó","seu pai","seu irmão",
            "idiota","burro","retardado","imbecil","otário"
        ]
        self.patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in blocked]
        # Contadores de avisos por usuário
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
            return
        if message.author.guild_permissions.administrator:
            return

        # procura palavrão
        for patt in self.patterns:
            if patt.search(message.content):
                try:
                    await message.delete()
                except discord.Forbidden:
                    return

                gid = str(message.guild.id)
                uid = str(message.author.id)
                # atualiza contador
                guild_warns = self.warns.setdefault(gid, {})
                count = guild_warns.get(uid, 0) + 1
                guild_warns[uid] = count
                self.save_state()

                # monta embed de aviso
                embed = discord.Embed(
                    title="🚫 Linguagem Proibida",
                    description=(
                        f"{message.author.mention}, não é permitido xingar aqui no servidor **{message.guild.name}**.\n"
                        f"Você recebeu **{count}** aviso(s) e pode ser banido se continuar.\n"
                        "Por favor, leia as regras do servidor."
                    ),
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=f"{message.guild.name}")
                embed.set_thumbnail(url=message.author.display_avatar.url)

                await message.channel.send(embed=embed, delete_after=15)

                # se quiser expulsar após 5 avisos, descomente:
                # if count >= self.DEFAULT_LIMIT:
                #     await message.guild.kick(message.author, reason="Limite de xingamentos")
                #     guild_warns.pop(uid, None)
                #     self.save_state()

                return  # processa só uma vez por mensagem

        # permite que comandos ainda funcionem
        await self.bot.process_commands(message)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
