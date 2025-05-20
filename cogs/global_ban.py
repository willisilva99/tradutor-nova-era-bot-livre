# cogs/global_ban.py
"""
GlobalBan – banimento global em todos os servidores do bot.
Requer tabelas:
    • GlobalBan              (histórico)
    • GlobalBanLogConfig     (canal de log + set_by)
"""
import asyncio, logging, time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from db import SessionLocal, GlobalBan, GlobalBanLogConfig

logger = logging.getLogger(__name__)

# ══════════════ Embeds helper ══════════════
class E:
    @staticmethod
    def _b(t, d, c):
        return discord.Embed(title=t, description=d, colour=c,
                             timestamp=datetime.now(timezone.utc))

    @staticmethod
    def _final(embed, *, footer=None, thumbnail_url=None):
        if footer:          embed.set_footer(text=footer)
        if thumbnail_url:   embed.set_thumbnail(url=thumbnail_url)
        return embed

    @classmethod
    def ok  (cls, d, **k): return cls._final(cls._b("✅ Sucesso",     d, discord.Color.green()), **k)
    @classmethod
    def err (cls, d, **k): return cls._final(cls._b("❌ Erro",        d, discord.Color.red()),   **k)
    @classmethod
    def info(cls, d, **k): return cls._final(cls._b("ℹ️ Informação", d, discord.Color.blue()),  **k)

# ══════════════ DB helper ══════════════
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

# ══════════════ Cog ══════════════
class GlobalBanCog(commands.Cog):
    RATE_LIMIT = 30
    REASONS    = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban = 0.0
        self.log_channels: dict[int, Optional[int]] = {}
        self.ban_cache: set[int] = set()

        self.gban = app_commands.Group(name="gban", description="Comandos de ban global")
        self._register_slash_commands()

    # ───── lifecycle ─────
    async def cog_load(self):
        await self._cache_log_channels()
        await self._load_ban_cache()
        self.bot.tree.add_command(self.gban)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.gban.name, type=self.gban.type)

    # ───── cache ─────
    async def _cache_log_channels(self):
        with db() as s:
            self.log_channels = {int(r.guild_id): int(r.channel_id)
                                 for r in s.query(GlobalBanLogConfig)}

    async def _load_ban_cache(self):
        with db() as s:
            self.ban_cache = {int(r.discord_id)
                              for r in s.query(GlobalBan.discord_id)}
        logger.info("[GlobalBan] cache %d IDs", len(self.ban_cache))

    # ───── logging util ─────
    async def _send_log(self, g: discord.Guild, embed: discord.Embed):
        ch = g.get_channel(self.log_channels.get(g.id, 0)) or g.system_channel
        if ch and ch.permissions_for(g.me).send_messages:
            await ch.send(embed=embed)

    async def _broadcast(self, embed: discord.Embed, guilds: List[discord.Guild]):
        await asyncio.gather(*(self._send_log(g, embed) for g in guilds))

    # ───── helpers DB ban ─────
    def _add_ban_db(self, uid: int, by: int, reason: str) -> bool:
        with db() as s:
            if s.query(GlobalBan).filter_by(discord_id=str(uid)).first():
                return False
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _del_ban_db(self, uid: int) -> int:
        with db() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(uid)).delete()

    # ───── mass util ─────
    async def _mass(self, guilds, fn) -> Tuple[List[discord.Guild], List[str]]:
        res = await asyncio.gather(*(fn(g) for g in guilds), return_exceptions=True)
        ok, fail = [], []
        for g, r in zip(guilds, res):
            (ok if not isinstance(r, Exception) else fail).append(g)
        return ok, [f.name for f in fail]

    # ───── eventos ─────
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        if m.id in self.ban_cache:
            try:
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban")
                await self._send_log(m.guild, E.ok(f"{m.mention} auto-banido (global)."))
            except discord.Forbidden:
                pass

    # ───── exec helpers ─────
    async def _exec_ban(self, user: discord.User, moderator, reason: str):
        if time.time() - self.last_gban < self.RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.RATE_LIMIT}s entre bans.")

        ok, fail = await self._mass(self.bot.guilds,
                                    lambda g: g.ban(user, reason=f"[GlobalBan] {reason}"))
        if self._add_ban_db(user.id, moderator.id, reason):
            self.ban_cache.add(user.id)
        self.last_gban = time.time()

        try:
            await user.send(embed=E.info(f"Você foi **banido globalmente**.\nMotivo: **{reason}**"))
        except discord.HTTPException:
            pass

        desc = (f"**Usuário:** {user} (`{user.id}`)\n"
                f"**Motivo:** {reason}\n"
                f"**Servidores banidos:** {len(ok)}/{len(self.bot.guilds)}")
        if fail:
            desc += f"\n⚠️ Falhou em: {', '.join(fail)}"
        embed = E.ok(desc, footer=f"Banido por {moderator}", thumbnail_url=user.display_avatar.url)
        await self._broadcast(embed, ok)
        return embed

    async def _exec_unban(self, uid: int, moderator):
        ok, fail = await self._mass(self.bot.guilds,
                                    lambda g: g.unban(discord.Object(id=uid), reason="[GlobalUnban]"))
        removed = self._del_ban_db(uid)
        self.ban_cache.discard(uid)

        desc = (f"**Usuário ID:** `{uid}`\n"
                f"**Desbanido em:** {len(ok)}/{len(self.bot.guilds)} servidores\n"
                f"**Registros removidos:** {removed}")
        if fail:
            desc += f"\n⚠️ Falhou em: {', '.join(fail)}"
        embed = E.ok(desc, footer=f"Unban por {moderator}")
        await self._broadcast(embed, ok)
        return embed

    # ───── prefix commands ─────
    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gban")
    async def gban_prefix(self, ctx, target: discord.User, *, reason="Sem Motivo"):
        try:
            embed = await self._exec_ban(target, ctx.author, reason)
        except RuntimeError as e:
            return await ctx.send(embed=E.err(str(e)))
        await ctx.send(embed=embed)

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gunban")
    async def gunban_prefix(self, ctx, target_id: int):
        embed = await self._exec_unban(target_id, ctx.author)
        await ctx.send(embed=embed)

    # ───── slash commands ─────
    def _register_slash_commands(self):
        admin_chk = lambda i: i.user.guild_permissions.administrator

        # /gban add
        @self.gban.command(name="add", description="Ban global")
        @app_commands.check(admin_chk)
        @app_commands.describe(reason="Motivo do ban")
        @app_commands.choices(reason=[app_commands.Choice(name=r, value=r) for r in self.REASONS])
        async def _add(inter: discord.Interaction, target: discord.User, reason: str = "Sem Motivo"):
            await inter.response.defer(thinking=True)
            try:
                embed = await self._exec_ban(target, inter.user, reason)
            except RuntimeError as e:
                await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
            else:
                await inter.followup.send(embed=embed)

        # /gban remove
        @self.gban.command(name="remove", description="Unban global")
        @app_commands.check(admin_chk)
        async def _remove(inter: discord.Interaction, target_id: int):
            await inter.response.defer(thinking=True)
            embed = await self._exec_unban(target_id, inter.user)
            await inter.followup.send(embed=embed)

        # /gban list
        @self.gban.command(name="list", description="Lista bans globais")
        @app_commands.check(admin_chk)
        async def _list(inter: discord.Interaction, page: int = 1):
            with db() as s:
                bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()
            if not bans:
                return await inter.response.send_message(embed=E.info("Nenhum ban registrado."), ephemeral=True)

            PER = 10
            pages = (len(bans) + PER - 1) // PER
            page = max(1, min(page, pages))

            def make(idx: int):
                chunk = bans[idx*PER:(idx+1)*PER]
                lines = [
                    f"`{b.discord_id}` • {b.reason} • banido por <@{int(b.banned_by)}>"
                    f" • <t:{int(b.timestamp.timestamp())}:R>"
                    for b in chunk
                ]
                return E.info("\n".join(lines), footer=f"Pág {idx+1}/{pages}")

            class Pager(discord.ui.View):
                def __init__(self, idx=page-1):
                    super().__init__(timeout=60); self.idx = idx
                @discord.ui.button(label="◀️")
                async def prev(self, _, i):
                    if self.idx > 0:
                        self.idx -= 1
                        await i.response.edit_message(embed=make(self.idx), view=self)
                @discord.ui.button(label="▶️")
                async def nxt(self, _, i):
                    if self.idx < pages-1:
                        self.idx += 1
                        await i.response.edit_message(embed=make(self.idx), view=self)

            await inter.response.send_message(embed=make(page-1), view=Pager(), ephemeral=True)

        # /gban setlog
        @self.gban.command(name="setlog", description="Define canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _setlog(inter: discord.Interaction, channel: discord.TextChannel):
            # verifica configuração existente
            current_id = self.log_channels.get(inter.guild.id)
            if current_id is not None and int(current_id) == channel.id:
                return await inter.response.send_message(
                    embed=E.info(f"Canal já estava configurado para {channel.mention}."), ephemeral=True)

            with db() as s:
                s.merge(GlobalBanLogConfig(guild_id=str(inter.guild.id),
                                           channel_id=str(channel.id),
                                           set_by=str(inter.user.id)))
            self.log_channels[inter.guild.id] = channel.id
            await inter.response.send_message(
                embed=E.ok(f"Canal de logs definido para {channel.mention}."), ephemeral=True)

        # /gban removelog
        @self.gban.command(name="removelog", description="Remove a configuração de log")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _removelog(inter: discord.Interaction):
            if inter.guild.id not in self.log_channels:
                return await inter.response.send_message(
                    embed=E.info("Nenhum canal de log estava configurado."), ephemeral=True)

            with db() as s:
                s.query(GlobalBanLogConfig).filter_by(guild_id=str(inter.guild.id)).delete()
            self.log_channels.pop(inter.guild.id, None)
            await inter.response.send_message(embed=E.ok("Canal de log removido."), ephemeral=True)

    # ───── slash error handler ─────
    @commands.Cog.listener()
    async def on_app_command_error(self, inter, error):
        if isinstance(error, app_commands.MissingPermissions):
            await inter.response.send_message(embed=E.err("Você não tem permissão."), ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            await inter.response.send_message(embed=E.err("Apenas administradores."), ephemeral=True)
        else:
            logger.exception("Slash error", exc_info=error)
            if not inter.response.is_done():
                await inter.response.send_message(
                    embed=E.err(f"Erro inesperado: {error.__class__.__name__}"), ephemeral=True)

# ═════════ setup ═════════
async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
