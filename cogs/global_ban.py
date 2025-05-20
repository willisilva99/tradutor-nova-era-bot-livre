# cogs/global_ban.py
import asyncio, logging, time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from db import SessionLocal, GlobalBan, GuildConfig

logger = logging.getLogger(__name__)

# ───────────── Embed util ─────────────
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

# ───────────── DB helper ─────────────
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

# ───────────── check owner ─────────────
OWNER_ID = 470628393272999948
def is_owner(inter: discord.Interaction) -> bool:
    return inter.user.id == OWNER_ID

# ───────────── GlobalBanCog ─────────────
class GlobalBanCog(commands.Cog):
    TRUSTED_IDS     = {OWNER_ID}
    GBAN_RATE_LIMIT = 30
    REASONS         = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    gban = app_commands.Group(name="gban", description="Comandos de ban global")

    # --------------- init ---------------
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban_ts = 0.0
        self.log_channels: dict[int, Optional[int]] = {}
        self.ban_cache: set[int] = set()

        self._cache_log_channels()
        bot.loop.create_task(self._load_ban_cache())
        bot.loop.create_task(self._health_check())

    # --------------- cache & health ---------------
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
                logger.warning("⚠️ Sem permissão de banir em: %s", g.name)

    # --------------- helpers ---------------
    async def _send_in_log(self, guild: discord.Guild, embed: discord.Embed):
        ch_id = self.log_channels.get(guild.id)
        channel = guild.get_channel(ch_id) if ch_id else guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)

    async def _broadcast(self, embed, guilds):
        await asyncio.gather(*(self._send_in_log(g, embed) for g in guilds))

    async def _mass(self, guilds, coro_factory):
        tasks = [coro_factory(g) for g in guilds]
        res = await asyncio.gather(*tasks, return_exceptions=True)
        ok, fail = [], []
        for g, r in zip(guilds, res):
            (ok if not isinstance(r, Exception) else fail).append(g)
        return ok, [f.name for f in fail]

    # --------------- DB ---------------
    def _add_db(self, uid, by, reason):
        with db() as s:
            if s.query(GlobalBan).filter_by(discord_id=str(uid)).first():
                return False
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _del_db(self, uid):
        with db() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(uid)).delete()

    # --------------- eventos ---------------
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        if m.id in self.ban_cache and m.id not in self.TRUSTED_IDS:
            try:
                await m.guild.ban(m, reason="[GlobalBan] Auto-ban")
                await self._send_in_log(m.guild, E.ok(f"{m.mention} auto-banido (global)."))
            except discord.Forbidden:
                pass

    # --------------- core ban/unban ---------------
    async def _exec_ban(self, user, mod, reason):
        if time.time() - self.last_gban_ts < self.GBAN_RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.GBAN_RATE_LIMIT}s entre bans.")
        if user.id in self.TRUSTED_IDS:
            raise RuntimeError("ID protegido.")

        ok, fail = await self._mass(self.bot.guilds,
                                    lambda g: g.ban(user, reason=f"[GlobalBan] {reason}"))
        if self._add_db(user.id, mod.id, reason):
            self.ban_cache.add(user.id)
        self.last_gban_ts = time.time()

        desc = f"**Usuário:** {user} (`{user.id}`)\n**Motivo:** {reason}\n" \
               f"**Servidores banidos:** {len(ok)}/{len(self.bot.guilds)}"
        if fail:
            desc += f"\n⚠️ Falhou em: {', '.join(fail)}"
        emb = E.ok(desc, footer=f"Banido por {mod}", thumbnail_url=user.display_avatar.url)
        await self._broadcast(emb, ok)
        return emb

    async def _exec_unban(self, uid, mod):
        ok, fail = await self._mass(self.bot.guilds,
                                    lambda g: g.unban(discord.Object(id=uid), reason="[GlobalUnban]"))
        deleted = self._del_db(uid); self.ban_cache.discard(uid)
        desc = f"**Usuário ID:** `{uid}`\n**Servidores desbanidos:** {len(ok)}/{len(self.bot.guilds)}\n" \
               f"**Registros removidos:** {deleted}"
        if fail: desc += f"\n⚠️ Falhou em: {', '.join(fail)}"
        emb = E.ok(desc, footer=f"Unban por {mod}")
        await self._broadcast(emb, ok)
        return emb

    # --------------- prefix ---------------
    @commands.is_owner()
    @commands.command(name="gban")
    async def gban_p(self, ctx, target: discord.User, *, reason="Sem Motivo"):
        try:
            emb = await self._exec_ban(target, ctx.author, reason)
        except RuntimeError as e:
            return await ctx.send(embed=E.err(str(e)))
        await ctx.send(embed=emb)

    @commands.is_owner()
    @commands.command(name="gunban")
    async def gunban_p(self, ctx, target_id: int):
        emb = await self._exec_unban(target_id, ctx.author)
        await ctx.send(embed=emb)

    # --------------- slash: add/remove ---------------
    @gban.command(name="add", description="Ban global")
    @app_commands.check(is_owner)
    @app_commands.describe(reason="Motivo")
    @app_commands.choices(reason=[app_commands.Choice(name=r, value=r) for r in REASONS])
    async def gban_add(self, inter: discord.Interaction, target: discord.User, reason: str = "Sem Motivo"):
        await inter.response.defer(thinking=True)
        try:
            emb = await self._exec_ban(target, inter.user, reason)
        except RuntimeError as e:
            return await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
        await inter.followup.send(embed=emb)

    @gban.command(name="remove", description="Unban global")
    @app_commands.check(is_owner)
    async def gban_remove(self, inter: discord.Interaction, target_id: int):
        await inter.response.defer(thinking=True)
        emb = await self._exec_unban(target_id, inter.user)
        await inter.followup.send(embed=emb)

    # --------------- slash: list ---------------
    @gban.command(name="list", description="Lista bans globais")
    @app_commands.check(is_owner)
    async def gban_list(self, inter: discord.Interaction, page: int = 1):
        with db() as s:
            bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()
        if not bans:
            return await inter.response.send_message(embed=E.info("Nenhum ban registrado."), ephemeral=True)

        per = 10
        pages = (len(bans) + per - 1) // per
        page = max(1, min(page, pages))

        def make(idx: int) -> discord.Embed:
            start, end = idx * per, idx * per + per
            lines = [f"`{b.discord_id}` • {b.reason} • <t:{int(b.timestamp.timestamp())}:R>"
                     for b in bans[start:end]]
            return E.info("\n".join(lines), footer=f"Pág {idx+1}/{pages}")

        class Pager(discord.ui.View):
            def __init__(self, idx=page-1):
                super().__init__(timeout=60)
                self.idx = idx

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.gray)
            async def prev(self, _, interaction: discord.Interaction):
                if self.idx > 0:
                    self.idx -= 1
                    await interaction.response.edit_message(embed=make(self.idx), view=self)

            @discord.ui.button(label="▶️", style=discord.ButtonStyle.gray)
            async def nxt(self, _, interaction: discord.Interaction):
                if self.idx < pages - 1:
                    self.idx += 1
                    await interaction.response.edit_message(embed=make(self.idx), view=self)

        await inter.response.send_message(embed=make(page-1), view=Pager(), ephemeral=True)

    # --------------- slash: setlog ---------------
    @gban.command(name="setlog", description="Define canal de logs")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gban_setlog(self, inter: discord.Interaction, channel: discord.TextChannel):
        with db() as s:
            cfg = s.merge(GuildConfig(guild_id=str(inter.guild.id)))
            cfg.log_channel_id = str(channel.id)
        self.log_channels[inter.guild.id] = channel.id
        await inter.response.send_message(embed=E.ok(f"Canal definido para {channel.mention}"), ephemeral=True)

    # --------------- error handler ---------------
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(embed=E.err("Somente o owner usa este comando."))
        else:
            logger.exception("Erro no GlobalBan")
            await ctx.send(embed=E.err(f"Erro inesperado: {error}"))

# --------------- setup ---------------
async def setup(bot):
    await bot.add_cog(GlobalBanCog(bot))
