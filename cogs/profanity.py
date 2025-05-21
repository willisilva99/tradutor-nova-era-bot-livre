# cogs/profanity.py
import re
import os
import json
import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class EmbedFactory:
    @staticmethod
    def base(title, description, color, author: discord.Member = None, thumbnail: str = None, footer: str = None):
        e = discord.Embed(
            title=title, description=description,
            color=color, timestamp=datetime.now(timezone.utc)
        )
        if author:
            e.set_author(name=str(author), icon_url=author.display_avatar.url)
        if thumbnail:
            e.set_thumbnail(url=thumbnail)
        if footer:
            e.set_footer(text=footer)
        return e

    @staticmethod
    def warning(member: discord.Member, bad_word: str, count: int, limit: int, rules_channel: discord.TextChannel):
        desc = (
            f"{member.mention}, sua mensagem foi removida por conter `{bad_word}`.\n"
            f"Você tem **{count}/{limit}** avisos.\n"
            f"Leia as regras em {rules_channel.mention}."
        )
        return EmbedFactory.base(
            "⚠️ Filtro de Linguagem",
            desc,
            color=discord.Color.orange(),
            author=member,
            thumbnail=member.display_avatar.url,
            footer=f"{member.guild.name}"
        )

    @staticmethod
    def expelled(member: discord.Member, limit: int):
        desc = f"{member.mention} foi expulso após atingir **{limit}/{limit}** avisos."
        return EmbedFactory.base(
            "👢 Expulsão Automática",
            desc,
            color=discord.Color.red(),
            author=member,
            thumbnail=member.display_avatar.url
        )

    @staticmethod
    def info(description: str, title="ℹ️ Informação"):
        return EmbedFactory.base(title, description, color=discord.Color.blue())

    @staticmethod
    def error(description: str, title="❌ Erro"):
        return EmbedFactory.base(title, description, color=discord.Color.red())

class ProfanityCog(commands.Cog):
    STATE_FILE = "profanity_state.json"
    DEFAULT_LIMIT = 5

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}
        self.patterns = [re.compile(rf"\b{w}\b", re.IGNORECASE) for w in [
            "porra","caralho","merda","puta","cacete","fodase","foda-se",
            "filhodaputa","filho da puta","vai se foder","vai te catar",
            "viado","bicha","traveco","tchola","macaco","negro de merda","crioulada",
            "sua mãe","sua avó","seu pai","seu irmão","idiota","burro","retardado","imbecil","otário"
        ]]
        self.load_state()

    def cog_unload(self):
        self.save_state()

    def load_state(self):
        if os.path.isfile(self.STATE_FILE):
            with open(self.STATE_FILE, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def save_state(self):
        with open(self.STATE_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def get_conf(self, guild: discord.Guild):
        gid = str(guild.id)
        conf = self.data.setdefault(gid, {})
        conf.setdefault("warns", {})
        conf.setdefault("limit", self.DEFAULT_LIMIT)
        conf.setdefault("rules", None)
        return conf

    def get_rules_channel(self, guild: discord.Guild):
        conf = self.get_conf(guild)
        cid = conf["rules"]
        return guild.get_channel(cid) if cid and guild.get_channel(cid) else guild.system_channel

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.administrator:
            return

        conf = self.get_conf(message.guild)
        limit = conf["limit"]
        rules_chan = self.get_rules_channel(message.guild)

        for patt in self.patterns:
            m = patt.search(message.content)
            if not m:
                continue

            bad_word = m.group(0)
            try:
                await message.delete()
            except discord.Forbidden:
                return

            uid = str(message.author.id)
            warns = conf["warns"]
            count = warns.get(uid, 0) + 1
            warns[uid] = count
            self.save_state()

            embed = EmbedFactory.warning(message.author, bad_word, count, limit, rules_chan)
            await message.channel.send(embed=embed)

            if count >= limit:
                try:
                    await message.guild.kick(message.author, reason="Limite de avisos atingido")
                    kicked_embed = EmbedFactory.expelled(message.author, limit)
                    await message.channel.send(embed=kicked_embed)
                except discord.Forbidden:
                    await message.channel.send(
                        f"❌ Não tenho permissão para expulsar {message.author.mention}."
                    )
                warns.pop(uid, None)
                self.save_state()
            return

    filter_group = app_commands.Group(name="filter", description="Configurações de aviso de linguagem")

    @filter_group.command(name="status", description="Mostra avisos de um usuário")
    @app_commands.describe(user="Membro a consultar")
    async def status(self, interaction: discord.Interaction, user: discord.Member):
        conf = self.get_conf(interaction.guild)
        count = conf["warns"].get(str(user.id), 0)
        embed = EmbedFactory.info(f"{user.mention} tem **{count}/{conf['limit']}** avisos.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @filter_group.command(name="reset", description="Redefine avisos de um usuário")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user="Membro alvo")
    async def reset(self, interaction: discord.Interaction, user: discord.Member):
        conf = self.get_conf(interaction.guild)
        conf["warns"].pop(str(user.id), None)
        self.save_state()
        embed = EmbedFactory.success(f"Avisos de {user.mention} foram redefinidos.")
        await interaction.response.send_message(embed=embed)

    @filter_group.command(name="limit", description="Define limite de avisos até expulsão")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(limit="Novo limite de avisos (1-10)")
    async def limit(self, interaction: discord.Interaction, limit: int):
        conf = self.get_conf(interaction.guild)
        conf["limit"] = max(1, min(10, limit))
        self.save_state()
        embed = EmbedFactory.success(f"Limite de avisos definido para **{conf['limit']}**.")
        await interaction.response.send_message(embed=embed)

    @filter_group.command(name="rules", description="Define canal de regras do servidor")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="Canal de regras")
    async def rules(self, interaction: discord.Interaction, channel: discord.TextChannel):
        conf = self.get_conf(interaction.guild)
        conf["rules"] = channel.id
        self.save_state()
        embed = EmbedFactory.success(f"Canal de regras setado para {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = EmbedFactory.error("Permissão insuficiente.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.exception(error)
            embed = EmbedFactory.error("Ocorreu um erro interno.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityCog(bot))
