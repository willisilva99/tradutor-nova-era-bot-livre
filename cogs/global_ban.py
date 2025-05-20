# cogs/global_ban.py
import asyncio, logging, time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Tuple, Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import SessionLocal, GlobalBan, GuildConfig

logger = logging.getLogger(__name__)


# ────────────────────────── Embed util ──────────────────────────
class E:
    @staticmethod
    def _b(title, desc, color):
        return discord.Embed(
            title=title,
            description=desc,
            colour=color,
            timestamp=datetime.now(timezone.utc),
        )

    ok   = staticmethod(lambda d, **k: E._b("✅ Sucesso",     d, discord.Color.green()).set_footer(**k))
    err  = staticmethod(lambda d, **k: E._b("❌ Erro",        d, discord.Color.red())  .set_footer(**k))
    info = staticmethod(lambda d, **k: E._b("ℹ️ Informação", d, discord.Color.blue()) .set_footer(**k))


# ────────────────────────── DB helper ───────────────────────────
@contextmanager
def db():  # usage:  with db() as s: ...
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ────────────────────────── Global Ban Cog ──────────────────────
class GlobalBanCog(commands.GroupCog, name="gban"):
    OWNER_ID        = 470628393272999948
    TRUSTED_IDS     = {470628393272999948}             # nunca poderão ser banidos
    GBAN_RATE_LIMIT = 30                               # seg. entre gban
    REASONS         = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban_ts: float = 0.0
        self.log_channels: dict[int, Optional[int]] = {}   # guild_id -> channel_id|None
        self.ban_cache: set[int] = set()                   # mem cache ids banidos

        self._cache_log_channels()
        self.bot.loop.create_task(self._load_ban_cache())
        self.bot.loop.create_task(self._health_check())

    # ────────────────── CACHE & HEALTH ──────────────────
    def _cache_log_channels(self):
        with db() as s:
            for cfg in s.query(GuildConfig).all():
                self.log_channels[int(cfg.guild_id)] = (
                    int(cfg.log_channel_id) if cfg.log_channel_id else None
                )

    async def _load_ban_cache(self):
        await self.bot.wait_until_ready()
        with db() as s:
            self.ban_cache = {int(r.discord_id) for r in s.query(GlobalBan.discord_id)}
        logger.info("GlobalBan cache carregado (%d IDs).", len(self.ban_cache))

    async def _health_check(self):
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            if not g.me.guild_permissions.ban_members:
                logger.warning("⚠️  Sem permissão de banir em: %s (%s)", g.name, g.id)

    # ────────────────── UTILS ──────────────────
    async def _send_in_log(self, guild: discord.Guild, embed: discord.Embed):
        chan_id = self.log_channels.get(guild.id)
        channel = guild.get_channel(chan_id) if chan_id else guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Falha ao enviar log em %s", guild.name)

    async def _broadcast(self, embed: discord.Embed, guilds: List[discord.Guild]):
        for g in guilds:
            await self._send_in_log(g, embed)

    async def _mass_action(
        self, guilds: List[discord.Guild], action_factory
    ) -> Tuple[List[discord.Guild], List[str]]:
        tasks = [action_factory(g) for g in guilds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ok, fail = [], []
        for g, r in zip(guilds, results):
            if isinstance(r, Exception):
                fail.append(g.name)
                logger.debug("Falha em %s: %s", g.name, r.__class__.__name__)
            else:
                ok.append(g)
        return ok, fail

    # ────────────────── DB helpers ──────────────────
    def _add_ban_db(self, uid: int, by: int, reason: str) -> bool:
        with db() as s:
            if s.query(GlobalBan).filter_by(discord_id=str(uid)).first():
                return False  # duplicado
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _remove_ban_db(self, uid: int) -> int:
        with db() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(uid)).delete()

    # ────────────────── Eventos ──────────────────
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        if m.id in self.ban_cache and m.id not in self.TRUSTED_IDS:
            try:
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban on join")
                embed = E.ok(f"{m.mention} foi **auto-banido** (global ban).")
                await self._send_in_log(m.guild, embed)
            except discord.Forbidden:
                pass

    # ────────────────── Core exec helpers ──────────────────
    async def _exec_ban(self, user: discord.User, moderator, reason: str):
        # rate-limit
        if time.time() - self.last_gban_ts < self.GBAN_RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.GBAN_RATE_LIMIT}s entre bans.")

        if user.id in self.TRUSTED_IDS:
            raise RuntimeError("Este ID está na lista Trusted e não pode ser banido.")

        guilds = self.bot.guilds
        ok, fail = await self._mass_action(
            guilds, lambda g: g.ban(user, reason=f"[GlobalBan] {reason}")
        )

        inserted = self._add_ban_db(user.id, moderator.id, reason)
        if inserted:
            self.ban_cache.add(user.id)

        self.last_gban_ts = time.time()

        msg = (
            f"**Usuário:** {user} (`{user.id}`)\n"
            f"**Motivo:** {reason}\n"
            f"**Servidores banidos:** {len(ok)}/{len(guilds)}"
        )
        if fail:
            msg += f"\n⚠️ Falhou em: {', '.join(fail)}"

        # tenta linkar audit-log do 1º servidor banido
        if ok:
            try:
                entry = await ok[0].audit_logs(limit=1, action=discord.AuditLogAction.ban).flatten()
                if entry:
                    log_link = f"https://discord.com/channels/{ok[0].id}/{entry[0].id}"
                    msg += f"\n🔗 [Audit-Log]({log_link})"
            except Exception:
                pass

        embed = E.ok(msg, footer=f"Banido por {moderator}", thumbnail_url=user.display_avatar.url)

        # DM ao alvo
        try:
            await user.send(embed=E.info(f"Você foi **GLOBALMENTE BANIDO** por ***{reason}***."))
        except discord.Forbidden:
            pass

        await self._broadcast(embed, ok)
        return embed

    async def _exec_unban(self, uid: int, moderator):
        guilds = self.bot.guilds
        ok, fail = await self._mass_action(
            guilds, lambda g: g.unban(discord.Object(id=uid), reason="[GlobalUnban]")
        )

        deleted = self._remove_ban_db(uid)
        self.ban_cache.discard(uid)

        msg = (
            f"**Usuário ID:** `{uid}`\n"
            f"**Servidores desbanidos:** {len(ok)}/{len(guilds)}\n"
            f"**Registros removidos:** {deleted}"
        )
        if fail:
            msg += f"\n⚠️ Falhou em: {', '.join(fail)}"

        embed = E.ok(msg, footer=f"Unban por {moderator}")
        await self._broadcast(embed, ok)
        return embed

    # ────────────────── Prefix commands ──────────────────
    @commands.is_owner()
    @commands.command(name="gban")
    async def gban_prefix(self, ctx, target: discord.User, *, reason="Sem Motivo"):
        try:
            embed = await self._exec_ban(target, ctx.author, reason)
        except RuntimeError as e:
            return await ctx.send(embed=E.err(str(e)))
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(name="gunban")
    async def gunban_prefix(self, ctx, target_id: int):
        embed = await self._exec_unban(target_id, ctx.author)
        await ctx.send(embed=embed)

    # ────────────────── Slash group ──────────────────
    @app_commands.guild_only()
    class Slash(app_commands.Group, name="gban", description="Comandos de ban global"):
        pass

    # --- /gban add ---
    @Slash.command(name="add", description="Ban global")
    @app_commands.checks.is_owner()
    @app_commands.describe(reason="Motivo do ban")
    @app_commands.choices(reason=[app_commands.Choice(name=r, value=r) for r in REASONS])
    async def _g_add(self, inter, target: discord.User, reason: str = "Sem Motivo"):
        await inter.response.defer(thinking=True)
        try:
            embed = await self._exec_ban(target, inter.user, reason)
        except RuntimeError as e:
            return await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
        await inter.followup.send(embed=embed)

    # --- /gban remove ---
    @Slash.command(name="remove", description="Unban global")
    @app_commands.checks.is_owner()
    async def _g_remove(self, inter, target_id: int):
        await inter.response.defer(thinking=True)
        embed = await self._exec_unban(target_id, inter.user)
        await inter.followup.send(embed=embed)

    # --- /gban list (com paginação via botões) ---
    @Slash.command(name="list", description="Lista bans globais")
    @app_commands.checks.is_owner()
    async def _g_list(self, inter, page: int = 1):
        with db() as s:
            bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()
        if not bans:
            return await inter.response.send_message(embed=E.info("Nenhum ban registrado."), ephemeral=True)

        # monta páginas
        per = 10
        pages = [
            bans[i : i + per] for i in range(0, len(bans), per)
        ]
        page = max(1, min(page, len(pages)))

        def make_embed(idx):
            chunk = pages[idx]
            lines = [
                f"`{b.discord_id}` • {b.reason} • <t:{int(b.timestamp.timestamp())}:R>"
                for b in chunk
            ]
            return E.info("\n".join(lines), footer=f"Pág {idx+1}/{len(pages)}")

        class Pager(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.idx = page - 1
                self.message: discord.Message | None = None

            async def _show(self, inter):
                await inter.response.edit_message(embed=make_embed(self.idx), view=self)

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.gray)
            async def prev(self, _, inter):
                if self.idx:
                    self.idx -= 1
                    await self._show(inter)

            @discord.ui.button(label="▶️", style=discord.ButtonStyle.gray)
            async def nxt(self, _, inter):
                if self.idx < len(pages) - 1:
                    self.idx += 1
                    await self._show(inter)

        view = Pager()
        msg = await inter.response.send_message(embed=make_embed(page - 1), view=view, ephemeral=True)
        view.message = msg

    # --- /gban setlog ---
    @Slash.command(name="setlog", description="Define o canal de logs do GlobalBan")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _g_setlog(self, inter, channel: discord.TextChannel):
        with db() as s:
            cfg = s.merge(GuildConfig(guild_id=str(inter.guild.id)))
            cfg.log_channel_id = str(channel.id)
        self.log_channels[inter.guild.id] = channel.id
        await inter.response.send_message(
            embed=E.ok(f"Canal de log definido para {channel.mention}."), ephemeral=True
        )

    # ────────────────── Error Handler ──────────────────
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(embed=E.err("Somente o dono do bot pode usar este comando."))
        else:
            logger.exception("Erro no GlobalBan cog")
            await ctx.send(embed=E.err(f"Erro inesperado: {error}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
