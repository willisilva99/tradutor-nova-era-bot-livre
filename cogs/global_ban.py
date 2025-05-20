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

# ───────────────────────── Embed helper ─────────────────────────
class E:
    @staticmethod
    def _b(t, d, c):
        return discord.Embed(
            title=t, description=d, colour=c,
            timestamp=datetime.now(timezone.utc)
        )
    @staticmethod
    def _f(e: discord.Embed, *, footer: Optional[str] = None, thumb: Optional[str] = None):
        if footer:
            e.set_footer(text=footer)
        if thumb:
            e.set_thumbnail(url=thumb)
        return e
    ok   = classmethod(lambda cls, d, **k: cls._f(cls._b("✅ Sucesso",     d, discord.Color.green()), **k))
    err  = classmethod(lambda cls, d, **k: cls._f(cls._b("❌ Erro",        d, discord.Color.red()),   **k))
    info = classmethod(lambda cls, d, **k: cls._f(cls._b("ℹ️ Informação", d, discord.Color.blue()),  **k))

# ───────────────────────── DB helper ────────────────────────────
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

# ───────────────────────── Cog ──────────────────────────────────
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
        logger.info("[GlobalBan] cache carregado com %d IDs", len(self.ban_cache))

    # ───── periodic recheck ─────
    async def _periodic_recheck(self):
        await self.bot.wait_until_ready()
        while True:
            for guild in self.bot.guilds:
                # faz fetch de TODO membro (online ou não)
                async for member in guild.fetch_members(limit=None):
                    if member.id in self.ban_cache:
                        try:
                            await guild.ban(member, reason="[GlobalBan] Auto-ban periódico")
                            await self._log(guild, E.ok(f"{member.mention} banido (recheck global)."))
                        except discord.Forbidden:
                            logger.warning(f"[GlobalBan] sem permissão para banir {member.id} em {guild.id}")
                        except Exception as e:
                            logger.error(f"[GlobalBan] erro ao banir {member.id} em {guild.id}: {e}")
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
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban")
                await self._log(m.guild, E.ok(f"{m.mention} auto-banido (global)."))
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
        desc = (
            f"**Usuário:** {user} (`{user.id}`)\n"
            f"**Motivo:** {reason}\n"
            f"**Servidores banidos:** "
            f"{sum(1 for r in results if not isinstance(r, Exception))}/{len(results)}"
        )
        await asyncio.gather(
            *(self._log(g, E.ok(desc, footer=f"Banido por {mod}", thumb=user.display_avatar.url))
              for g, r in zip(self.bot.guilds, results) if not isinstance(r, Exception))
        )

    async def _exec_unban(self, uid: int, mod):
        results = await asyncio.gather(
            *(g.unban(discord.Object(id=uid), reason="[GlobalUnban]") for g in self.bot.guilds),
            return_exceptions=True
        )
        self._del_db(uid)
        self.ban_cache.discard(uid)
        desc = f"**Usuário ID:** `{uid}` banimento removido em " \
               f"{sum(1 for r in results if not isinstance(r, Exception))}/{len(results)} servidores"
        await asyncio.gather(
            *(self._log(g, E.ok(desc, footer=f"Unban por {mod}"))
              for g, r in zip(self.bot.guilds, results) if not isinstance(r, Exception))
        )

    # ───── prefix commands ─────
    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gban")
    async def _gban_prefix(self, ctx, alvo: discord.User, *, reason="Sem Motivo"):
        try:
            await self._exec_ban(alvo, ctx.author, reason)
            await ctx.message.add_reaction("✅")
        except RuntimeError as e:
            await ctx.send(embed=E.err(str(e)))

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gunban")
    async def _gunban_prefix(self, ctx, uid: int):
        await self._exec_unban(uid, ctx.author)
        await ctx.message.add_reaction("✅")

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
                await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
            else:
                await inter.followup.send(embed=E.ok("Ban aplicado."), ephemeral=True)

        @self.gban.command(name="remove", description="Unban global")
        @app_commands.check(admin)
        async def _remove(inter: discord.Interaction, target_id: int):
            await inter.response.defer(thinking=True)
            await self._exec_unban(target_id, inter.user)
            await inter.followup.send(embed=E.ok("Unban concluído."), ephemeral=True)

        @self.gban.command(name="setlog", description="Define canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _setlog(inter: discord.Interaction, channel: discord.TextChannel):
            cur = self.log_channels.get(inter.guild.id)
            if cur == channel.id:
                return await inter.response.send_message(
                    embed=E.info(f"Já configurado para {channel.mention}."), ephemeral=True)
            with db() as s:
                s.merge(GlobalBanLogConfig(
                    guild_id=str(inter.guild.id),
                    channel_id=str(channel.id),
                    set_by=str(inter.user.id)
                ))
            self.log_channels[inter.guild.id] = channel.id
            await inter.response.send_message(embed=E.ok(f"Canal definido: {channel.mention}"), ephemeral=True)

        @self.gban.command(name="removelog", description="Remove canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _removelog(inter: discord.Interaction):
            if inter.guild.id not in self.log_channels:
                return await inter.response.send_message(
                    embed=E.info("Nenhum canal configurado."), ephemeral=True)
            with db() as s:
                s.query(GlobalBanLogConfig).filter_by(guild_id=str(inter.guild.id)).delete()
            self.log_channels.pop(inter.guild.id, None)
            await inter.response.send_message(embed=E.ok("Canal de log removido."), ephemeral=True)

    # ───── error handler ─────
    @commands.Cog.listener()
    async def on_app_command_error(self, inter, error):
        if isinstance(error, (app_commands.CheckFailure, commands.MissingPermissions)):
            await inter.response.send_message(embed=E.err("Permissão insuficiente."), ephemeral=True)
        else:
            logger.exception("Slash error", exc_info=error)
            if not inter.response.is_done():
                await inter.response.send_message(embed=E.err("Erro inesperado."), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
