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
    Detecta xingamentos, remove a mensagem e envia um embed persistente
    com detalhes. Bane automaticamente após 10 avisos.
    """
    STATE_FILE = "profanity_state.json"
    DEFAULT_LIMIT = 10  # avisos até ban

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # lista de palavras proibidas
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

            # cria embed persistente
            now = datetime.now(timezone.utc)
            warn_embed = discord.Embed(
                title="⚠️ Linguagem Proibida Detectada",
                description=(
                    f"{message.author.mention}, sua mensagem continha **`{bad}`**, proibido neste servidor.\n\n"
                    f"**🔢 Avisos:** {count}/{self.DEFAULT_LIMIT}\n"
                    f"**📌 Servidor:** {message.guild.name}\n"
                    f"**🕒 Horário:** {now.strftime('%d/%m/%Y %H:%M:%S UTC')}\n\n"
                    f"Continuar pode resultar em banimento. Leia as regras em `#regras`."
                ),
                color=discord.Color.orange()
            )
            warn_embed.set_author(
                name=f"{message.author} ({message.author.display_name})",
                icon_url=message.author.display_avatar.url
            )
            warn_embed.set_thumbnail(url=message.author.display_avatar.url)
            warn_embed.add_field(name="💬 Mensagem Original", value=f"> {message.content[:1024]}", inline=False)
            warn_embed.set_footer(text=f"ID: {user_id}")

            await message.channel.send(embed=warn_embed)

            # ban automático após limite
            if count >= self.DEFAULT_LIMIT:
                try:
                    await message.guild.ban(message.author, reason="Limite de xingamentos atingido")
                except discord.Forbidden:
                    return

                ban_embed = discord.Embed(
                    title="🔨 Ban Automático Aplicado",
                    description=(
                        f"{message.author.mention} excedeu **{self.DEFAULT_LIMIT}** avisos e foi banido.\n\n"
                        f"**🆔 ID:** `{user_id}`\n"
                        f"**📌 Servidor:** {message.guild.name}\n"
                        f"**🕒 Horário:** {now.strftime('%d/%m/%Y %H:%M:%S UTC')}"
                    ),
                    color=discord.Color.red()
                )
                ban_embed.set_author(
                    name=f"{message.author} ({message.author.display_name})",
                    icon_url=message.author.display_avatar.url
                )
                ban_embed.set_thumbnail(url=message.author.display_avatar.url)
                ban_embed.set_footer(text="Ban aplicado automaticamente")

                await message.channel.send(embed=ban_embed)
                # reset contador
                guild_warns.pop(user_id, None)
                self.save_state()

            return

        # processa outros comandos normalmente
        await self.bot.process_commands(message)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
