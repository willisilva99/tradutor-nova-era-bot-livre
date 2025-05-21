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
    Cog separado para detecção de palavrões, avisos e expulsão após 5 infrações.
    """
    STATE_FILE = "profanity_state.json"
    MAX_WARNS = 5

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # lista de palavras proibidas
        blocked_words = [
            "porra", "caralho", "merda", "puta", "cacete", "fodase", "foda-se",
            "filhodaputa", "filho da puta", "vai se foder", "vai te catar",
            "viado", "bicha", "traveco", "tchola",
            "macaco", "negro de merda", "crioulada",
            "sua mãe", "sua avó", "seu pai", "seu irmão",
            "idiota", "burro", "retardado", "imbecil", "otário"
        ]
        self.blocked_patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in blocked_words]
        self.warns = {}  # { guild_id: { user_id: count } }

        self.load_state()

    def cog_unload(self):
        self.save_state()

    def save_state(self):
        data = {
            str(gid): uw
            for gid, uw in self.warns.items()
        }
        with open(self.STATE_FILE, "w") as f:
            json.dump(data, f)

    def load_state(self):
        if os.path.isfile(self.STATE_FILE):
            with open(self.STATE_FILE, "r") as f:
                data = json.load(f)
            self.warns = {
                int(gid): {int(uid): cnt for uid, cnt in uw.items()}
                for gid, uw in data.items()
            }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        for patt in self.blocked_patterns:
            m = patt.search(message.content)
            if not m:
                continue

            bad_word = m.group(0)
            try:
                await message.delete()
            except discord.Forbidden:
                return

            gid = message.guild.id
            uid = message.author.id
            # incrementa avisos
            self.warns.setdefault(gid, {})
            count = self.warns[gid].get(uid, 0) + 1
            self.warns[gid][uid] = count
            self.save_state()

            # embed de aviso
            embed = discord.Embed(
                title="⚠️ Aviso de Linguagem",
                color=discord.Color.orange(),
                description=(
                    f"{message.author.mention}, sua mensagem foi removida.\n"
                    f"Por favor, leia as regras do servidor."
                ),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.add_field(name="🆔 ID do Usuário",       value=f"`{uid}`", inline=True)
            embed.add_field(name="📋 Palavra Proibida",    value=f"`{bad_word}`", inline=True)
            embed.add_field(name="🔢 Avisos",              value=f"{count}/{self.MAX_WARNS}", inline=False)
            embed.set_footer(text=f"Após {self.MAX_WARNS} avisos, expulsão automática")

            await message.channel.send(embed=embed)

            # expulsão após limite
            if count >= self.MAX_WARNS:
                try:
                    await message.guild.kick(message.author, reason="5 avisos de xingamentos")
                    exp_embed = discord.Embed(
                        title="👢 Expulsão Automática",
                        color=discord.Color.red(),
                        description=(
                            f"{message.author.mention} foi expulso após {self.MAX_WARNS} avisos "
                            "de linguagem inapropriada."
                        ),
                        timestamp=datetime.now(timezone.utc)
                    )
                    exp_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                    exp_embed.add_field(name="🆔 ID do Usuário", value=f"`{uid}`", inline=True)
                    await message.channel.send(embed=exp_embed)
                except discord.Forbidden:
                    await message.channel.send(
                        f"❌ Não tenho permissão para expulsar {message.author.mention}."
                    )
                # reseta contador após expulsão
                del self.warns[gid][uid]
                self.save_state()

            return  # só dispara uma vez por mensagem

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
