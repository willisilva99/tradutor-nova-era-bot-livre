# cogs/global_ban.py
"""
GlobalBan – banimento global em todos os servidores do bot.
Necessita tabelas:
    • GlobalBan              (id, discord_id, banned_by, reason, timestamp)
    • GlobalBanLogConfig     (guild_id, channel_id, set_by)
"""
import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import SessionLocal, GlobalBan, GlobalBanLogConfig

logger = logging.getLogger(__name__)

# Somente este usuário pode ver a lista de servidores protegidos
PROTECTED_COMMAND_USER_ID = 470628393272999948

# ───────────────────────── Embed helper ─────────────────────────
class E:
    @staticmethod
    def _base(title: str, color: discord.Color, user: Optional[discord.User] = None):
        e = discord.Embed(title=title, colour=color, timestamp=datetime.now(timezone.utc))
        if user:
            e.set_author(name=str(user), icon_url=user.display_avatar.url)
            e.set_thumbnail(url=user.display_avatar.url)
        return e

    @classmethod
    def ban_manual(cls, user: discord.User, moderator: discord.User, reason: str):
        e = cls._base("🔨 Ban Global Aplicado", discord.Color.red(), user)
        e.add_field(name="🆔 ID",         value=f"`{user.id}`", inline=True)
        e.add_field(name="👮 Moderador", value=str(moderator), inline=True)
        e.add_field(name="📋 Motivo",     value=reason, inline=False)
        e.set_footer(text="Ban aplicado manualmente")
        return e

    @classmethod
    def ban_auto(cls, user: discord.User, context: str):
        if context == "on_member_join":
            title = "🚪 Auto-Ban à Entrada"
            desc = "Usuário entrou no servidor"
        else:
            title = "⏱️ Auto-Ban Periódico"
            desc = "Verificação periódica de membros"
        e = cls._base(title, discord.Color.orange(), user)
        e.add_field(name="🆔 ID",      value=f"`{user.id}`", inline=True)
        e.add_field(name="⚙️ Contexto", value=desc, inline=True)
        e.set_footer(text="Ban automático pelo GlobalBanCog")
        return e

    @classmethod
    def unban(cls, user_id: int, moderator: discord.User):
        e = discord.Embed(
            title="🔓 Unban Global Concluído",
            colour=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        e.add_field(name="🆔 ID",         value=f"`{user_id}`", inline=True)
        e.add_field(name="👮 Moderador", value=str(moderator), inline=True)
        e.set_footer(text="Unban processado")
        return e

    @classmethod
    def info(cls, desc: str):
        return discord.Embed(
            title="ℹ️ Informação",
            description=desc,
            colour=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

    @classmethod
    def error(cls, desc: str):
        return discord.Embed(
            title="❌ Erro",
            description=desc,
            colour=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

# ───────────────────────── DB helper ─────────────────────────────────
@contextmanager
def db():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

# ───────────────────────── Cog ────────────────────────────────────────
class GlobalBanCog(commands.Cog):
    RATE_LIMIT        = 30        # segundos entre bans via slash/prefix
    RECHECK_INTERVAL  = 5 * 60    # 5 minutos em segundos
    REASONS           = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban      = 0.0
        self.log_channels   = {}      # guild_id -> channel_id
        self.ban_cache      = set()   # conjunto de IDs banidos
        self.gban = app_commands.Group(name="gban", description="Comandos de ban global")
        self._register_slash_commands()

    async def cog_load(self):
        await self._cache_log_channels()
        await self._load_ban_cache()
        # inicia a task periódica de rechecagem
        self._rechecker_task = asyncio.create_task(self._periodic_recheck())
        self.bot.tree.add_command(self.gban)

    async def cog_unload(self):
        self._rechecker_task.cancel()
        self.bot.tree.remove_command(self.gban.name, type=self.gban.type)

    # ───── cache ─────
    async def _cache_log_channels(self):
        with db() as s:
            self.log_channels = {
                int(r.guild_id): int(r.channel_id)
                for r in s.query(GlobalBanLogConfig)
            }

    async def _load_ban_cache(self):
        with db() as s:
            self.ban_cache = {int(r.discord_id) for r in s.query(GlobalBan)}
        logger.info(f"[GlobalBan] cache carregado com {len(self.ban_cache)} IDs")

    # ───── periodic recheck ─────
    async def _periodic_recheck(self):
        await self.bot.wait_until_ready()
        while True:
            for guild in self.bot.guilds:
                async for member in guild.fetch_members(limit=None):
                    if member.id in self.ban_cache:
                        try:
                            await guild.ban(member, reason="[GlobalBan] Auto-ban periódico")
                            embed = E.ban_auto(member, "periodic")
                            await self._log(guild, embed)
                        except discord.Forbidden:
                            logger.warning(f"[GlobalBan] sem permissão para banir {member.id} em {guild.id}")
                        except Exception as e:
                            logger.error(f"[GlobalBan] erro ao banir {member.id}: {e}")
            await asyncio.sleep(self.RECHECK_INTERVAL)

    # ───── logging util ─────
    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch = guild.get_channel(self.log_channels.get(guild.id, 0)) or guild.system_channel
        if ch and ch.permissions_for(guild.me).send_messages:
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

    # ───── events ─────
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        if m.id in self.ban_cache:
            try:
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban à entrada")
                embed = E.ban_auto(m, "on_member_join")
                await self._log(m.guild, embed)
            except discord.Forbidden:
                logger.warning(f"[GlobalBan] sem permissão para banir {m.id} em {m.guild.id}")

    # ───── DB helpers ─────
    def _add_db(self, uid: int, by: int, reason: str) -> bool:
        with db() as s:
            if s.query(GlobalBan).filter_by(discord_id=str(uid)).first():
                return False
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _del_db(self, uid: int) -> int:
        with db() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(uid)).delete()

    # ───── ban & unban ─────
    async def _exec_ban(self, user: discord.User, mod, reason: str):
        if time.time() - self.last_gban < self.RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.RATE_LIMIT}s entre bans.")
        # tenta banir em todas as guildas
        results = await asyncio.gather(
            *(g.ban(user, reason=f"[GlobalBan] {reason}") for g in self.bot.guilds),
            return_exceptions=True
        )
        if self._add_db(user.id, mod.id, reason):
            self.ban_cache.add(user.id)
        self.last_gban = time.time()
        try:
            await user.send(embed=E.info(f"Você foi **banido globalmente**.\nMotivo: **{reason}**"))
        except discord.HTTPException:
            pass
        # monta embed de ban manual
        embed = E.ban_manual(user, mod, reason)
        # envia log apenas nas guildas que tiveram sucesso
        for guild, res in zip(self.bot.guilds, results):
            if not isinstance(res, Exception):
                await self._log(guild, embed)

    async def _exec_unban(self, uid: int, mod):
        results = await asyncio.gather(
            *(g.unban(discord.Object(id=uid), reason="[GlobalUnban]") for g in self.bot.guilds),
            return_exceptions=True
        )
        self._del_db(uid)
        self.ban_cache.discard(uid)
        embed = E.unban(uid, mod)
        for guild, res in zip(self.bot.guilds, results):
            if not isinstance(res, Exception):
                await self._log(guild, embed)

    # ───── prefix commands ─────
    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gban")
    async def _gban_prefix(self, ctx, alvo: discord.User, *, reason="Sem Motivo"):
        try:
            await self._exec_ban(alvo, ctx.author, reason)
            await ctx.message.add_reaction("✅")
        except RuntimeError as e:
            await ctx.send(embed=E.error(str(e)))

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gunban")
    async def _gunban_prefix(self, ctx, uid: int):
        await self._exec_unban(uid, ctx.author)
        await ctx.message.add_reaction("✅")

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="protected_servers")
    async def _protected_servers_prefix(self, ctx):
        """Mostra servidores protegidos (usuário autorizado somente)."""
        if ctx.author.id != PROTECTED_COMMAND_USER_ID:
            return await ctx.send(embed=E.error("Permissão negada."), delete_after=10)
        guilds = self.bot.guilds
        embed = discord.Embed(
            title="🤖 Servidores Protegidos",
            description=f"O bot está em **{len(guilds)}** servidores:",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        for g in guilds:
            embed.add_field(name=g.name, value=f"ID: `{g.id}` • Membros: {g.member_count}", inline=False)
        embed.set_footer(text=f"Solicitado por {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    # ───── slash commands ─────
    def _register_slash_commands(self):
        admin = lambda i: i.user.guild_permissions.administrator

        @self.gban.command(name="add", description="Ban global")
        @app_commands.check(admin)
        @app_commands.describe(reason="Motivo do ban")
        @app_commands.choices(reason=[app_commands.Choice(name=r, value=r) for r in self.REASONS])
        async def _add(inter: discord.Interaction, target: discord.User, reason: str = "Sem Motivo"):
            await inter.response.defer(thinking=True)
            try:
                await self._exec_ban(target, inter.user, reason)
            except RuntimeError as e:
                await inter.followup.send(embed=E.error(str(e)), ephemeral=True)
            else:
                await inter.followup.send(embed=E.ban_manual(target, inter.user, reason), ephemeral=True)

        @self.gban.command(name="remove", description="Unban global")
        @app_commands.check(admin)
        async def _remove(inter: discord.Interaction, target_id: int):
            await inter.response.defer(thinking=True)
            await self._exec_unban(target_id, inter.user)
            await inter.followup.send(embed=E.unban(target_id, inter.user), ephemeral=True)

        @self.gban.command(name="setlog", description="Define canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _setlog(inter: discord.Interaction, channel: discord.TextChannel):
            cur = self.log_channels.get(inter.guild.id)
            if cur == channel.id:
                return await inter.response.send_message(embed=E.info(f"Já configurado para {channel.mention}."), ephemeral=True)
            with db() as s:
                s.merge(GlobalBanLogConfig(
                    guild_id=str(inter.guild.id),
                    channel_id=str(channel.id),
                    set_by=str(inter.user.id)
                ))
            self.log_channels[inter.guild.id] = channel.id
            await inter.response.send_message(embed=E.info(f"Canal definido: {channel.mention}"), ephemeral=True)

        @self.gban.command(name="servers", description="Servidores protegidos pelo bot")
        @app_commands.check(lambda i: i.user.id == PROTECTED_COMMAND_USER_ID)
        async def _servers_slash(inter: discord.Interaction):
            guilds = self.bot.guilds
            embed = discord.Embed(
                title="🤖 Servidores Protegidos",
                description=f"O bot está em **{len(guilds)}** servidores:",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            for g in guilds:
                embed.add_field(name=g.name, value=f"ID: `{g.id}` • Membros: {g.member_count}", inline=False)
            embed.set_footer(text=f"Solicitado por {inter.user}", icon_url=inter.user.display_avatar.url)
            await inter.response.send_message(embed=embed, ephemeral=True)

        @self.gban.command(name="removelog", description="Remove canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _removelog(inter: discord.Interaction):
            if inter.guild.id not in self.log_channels:
                return await inter.response.send_message(embed=E.info("Nenhum canal configurado."), ephemeral=True)
            with db() as s:
                s.query(GlobalBanLogConfig).filter_by(guild_id=str(inter.guild.id)).delete()
            self.log_channels.pop(inter.guild.id, None)
            await inter.response.send_message(embed=E.info("Canal de log removido."), ephemeral=True)

    # ───── error handler ─────
    @commands.Cog.listener()
    async def on_app_command_error(self, inter, error):
        if isinstance(error, (app_commands.CheckFailure, commands.MissingPermissions)):
            await inter.response.send_message(embed=E.error("Permissão insuficiente."), ephemeral=True)
        else:
            logger.exception("Slash error", exc_info=error)
            if not inter.response.is_done():
                await inter.response.send_message(embed=E.error("Erro inesperado."), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
