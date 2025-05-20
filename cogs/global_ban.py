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

# ─────────── util embed ───────────
class E:
    @staticmethod
    def _b(title, desc, color):
        return discord.Embed(
            title=title, description=desc, colour=color,
            timestamp=datetime.now(timezone.utc)
        )
    ok   = staticmethod(lambda d, **k: E._b("✅ Sucesso",     d, discord.Color.green()).set_footer(**k))
    err  = staticmethod(lambda d, **k: E._b("❌ Erro",        d, discord.Color.red())  .set_footer(**k))
    info = staticmethod(lambda d, **k: E._b("ℹ️ Informação", d, discord.Color.blue()) .set_footer(**k))

# ─────────── DB helper ───────────
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

# ─────────── Global Ban Cog ───────────
class GlobalBanCog(commands.Cog):
    OWNER_ID        = 470628393272999948
    TRUSTED_IDS     = {470628393272999948}
    GBAN_RATE_LIMIT = 30
    REASONS         = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    # grupo de slash-commands declarado como **instância**
    gban_slash = app_commands.Group(
        name="gban",
        description="Comandos de ban global"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban_ts = 0.0
        self.log_channels: dict[int, Optional[int]] = {}
        self.ban_cache: set[int] = set()

        self._cache_log_channels()
        self.bot.loop.create_task(self._load_ban_cache())
        self.bot.loop.create_task(self._health_check())

    # ───── cache & health ─────
    def _cache_log_channels(self):
        with db() as s:
            for cfg in s.query(GuildConfig).all():
                self.log_channels[int(cfg.guild_id)] = int(cfg.log_channel_id) if cfg.log_channel_id else None

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

    # ───── util envio log ─────
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

    # ───── ações em lote ─────
    async def _mass_action(self, guilds, factory):
        tasks = [factory(g) for g in guilds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ok, fail = [], []
        for g, r in zip(guilds, results):
            (ok if not isinstance(r, Exception) else fail).append(g)
        return ok, [f.name for f in fail]

    # ───── DB helpers ─────
    def _add_ban_db(self, uid, by, reason):
        with db() as s:
            if s.query(GlobalBan).filter_by(discord_id=str(uid)).first():
                return False
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _remove_ban_db(self, uid):
        with db() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(uid)).delete()

    # ───── eventos ─────
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        if m.id in self.ban_cache and m.id not in self.TRUSTED_IDS:
            try:
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban on join")
                await self._send_in_log(m.guild, E.ok(f"{m.mention} auto-banido (global)."))
            except discord.Forbidden:
                pass

    # ───── exec helpers ─────
    async def _exec_ban(self, user, mod, reason):
        if time.time() - self.last_gban_ts < self.GBAN_RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.GBAN_RATE_LIMIT}s entre bans.")
        if user.id in self.TRUSTED_IDS:
            raise RuntimeError("ID protegido (Trusted).")

        ok, fail = await self._mass_action(
            self.bot.guilds, lambda g: g.ban(user, reason=f"[GlobalBan] {reason}")
        )
        if self._add_ban_db(user.id, mod.id, reason):
            self.ban_cache.add(user.id)
        self.last_gban_ts = time.time()

        desc = (
            f"**Usuário:** {user} (`{user.id}`)\n"
            f"**Motivo:** {reason}\n"
            f"**Servidores banidos:** {len(ok)}/{len(self.bot.guilds)}"
            + (f"\n⚠️ Falhou em: {', '.join(fail)}" if fail else "")
        )
        embed = E.ok(desc, footer=f"Banido por {mod}", thumbnail_url=user.display_avatar.url)
        await self._broadcast(embed, ok)
        return embed

    async def _exec_unban(self, uid, mod):
        ok, fail = await self._mass_action(
            self.bot.guilds, lambda g: g.unban(discord.Object(id=uid), reason="[GlobalUnban]")
        )
        deleted = self._remove_ban_db(uid)
        self.ban_cache.discard(uid)

        desc = (
            f"**Usuário ID:** `{uid}`\n"
            f"**Servidores desbanidos:** {len(ok)}/{len(self.bot.guilds)}\n"
            f"**Registros removidos:** {deleted}"
            + (f"\n⚠️ Falhou em: {', '.join(fail)}" if fail else "")
        )
        embed = E.ok(desc, footer=f"Unban por {mod}")
        await self._broadcast(embed, ok)
        return embed

    # ─── Prefix --------------
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

    # ─── Slash Group commands ------------
    @gban_slash.command(name="add", description="Ban global")
    @app_commands.checks.is_owner()
    @app_commands.describe(reason="Motivo do ban")
    @app_commands.choices(reason=[app_commands.Choice(name=r, value=r) for r in REASONS])
    async def gban_add(self, inter, target: discord.User, reason: str = "Sem Motivo"):
        await inter.response.defer(thinking=True)
        try:
            embed = await self._exec_ban(target, inter.user, reason)
        except RuntimeError as e:
            return await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
        await inter.followup.send(embed=embed)

    @gban_slash.command(name="remove", description="Unban global")
    @app_commands.checks.is_owner()
    async def gban_remove(self, inter, target_id: int):
        await inter.response.defer(thinking=True)
        embed = await self._exec_unban(target_id, inter.user)
        await inter.followup.send(embed=embed)

    # ---------- list com paginação ----------
    @gban_slash.command(name="list", description="Lista bans globais")
    @app_commands.checks.is_owner()
    async def gban_list(self, inter, page: int = 1):
        with db() as s:
            bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()
        if not bans:
            return await inter.response.send_message(embed=E.info("Nenhum ban registrado."), ephemeral=True)

        per, pages = 10, (len(bans) + 9) // 10
        page = max(1, min(page, pages))
        def make(idx):
            sl = bans[idx*per:(idx+1)*per]
            body = "\n".join(f"`{b.discord_id}` • {b.reason} • <t:{int(b.timestamp.timestamp())}:R>" for b in sl)
            return E.info(body, footer=f"Pág {idx+1}/{pages}")

        class View(discord.ui.View):
            def __init__(self, idx=page-1):
                super().__init__(timeout=60); self.idx=idx
            @discord.ui.button(label="◀️")
            async def prev(self, b, i):
                if self.idx: self.idx-=1; await i.response.edit_message(embed=make(self.idx), view=self)
            @discord.ui.button(label="▶️")
            async def nxt(self, b, i):
                if self.idx<pages-1: self.idx+=1; await i.response.edit_message(embed=make(self.idx), view=self)

        await inter.response.send_message(embed=make(page-1), view=View(), ephemeral=True)

    # ---------- setlog ----------
    @gban_slash.command(name="setlog", description="Define canal de logs do GlobalBan")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gban_setlog(self, inter, channel: discord.TextChannel):
        with db() as s:
            cfg = s.merge(GuildConfig(guild_id=str(inter.guild.id)))
            cfg.log_channel_id = str(channel.id)
        self.log_channels[inter.guild.id] = channel.id
        await inter.response.send_message(embed=E.ok(f"Canal definido: {channel.mention}"), ephemeral=True)

    # ---------- error handler ----------
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(embed=E.err("Somente o dono do bot usa este comando."))
        else:
            logger.exception("Erro no GlobalBan")
            await ctx.send(embed=E.err(f"Erro inesperado: {error}"))

# ---------- setup ----------
async def setup(bot):
    await bot.add_cog(GlobalBanCog(bot))
