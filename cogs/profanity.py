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
    DEFAULT_LIMIT = 10  # novos avisos até ban

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
        # warns por servidor e usuário
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
        # itera padrões
        for patt in self.patterns:
            m = patt.search(message.content)
            if not m:
                continue

            bad = m.group(0)
            # deleta mensagem
            try:
                await message.delete()
            except discord.Forbidden:
                return

            # incrementa contador
            g = self.warns.setdefault(guild_id, {})
            count = g.get(user_id, 0) + 1
            g[user_id] = count
            self.save_state()

            # embed de aviso
            warn_embed = discord.Embed(
                title="⚠️ Atenção!",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            warn_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            warn_embed.add_field(name="🚫 Palavra Proibida", value=f"`{bad}`", inline=True)
            warn_embed.add_field(name="🔢 Avisos", value=f"{count}/{self.DEFAULT_LIMIT}", inline=True)
            warn_embed.add_field(name="📋 Servidor", value=message.guild.name, inline=False)
            warn_embed.set_footer(text="Você pode ser banido se atingir 10 avisos")
            await message.channel.send(embed=warn_embed, delete_after=120)

            # ban automático após 10
            if count >= self.DEFAULT_LIMIT:
                try:
                    await message.guild.ban(message.author, reason="Limite de xingamentos atingido")
                except discord.Forbidden:
                    return

                # embed de ban
                ban_embed = discord.Embed(
                    title="🔨 Ban Automático",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                ban_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                ban_embed.add_field(name="🆔 ID", value=f"`{user_id}`", inline=True)
                ban_embed.add_field(name="⚠️ Total de Avisos", value=f"{count}/{self.DEFAULT_LIMIT}", inline=True)
                ban_embed.add_field(name="📋 Servidor", value=message.guild.name, inline=False)
                ban_embed.set_footer(text="Ban aplicado automaticamente!")
                await message.channel.send(embed=ban_embed, delete_after=120)

                # reset contador
                g.pop(user_id, None)
                self.save_state()

            return  # só processa uma detecção por mensagem

        # permite outros comandos
        await self.bot.process_commands(message)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
