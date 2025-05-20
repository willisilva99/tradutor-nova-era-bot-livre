import asyncio, logging, time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from db import SessionLocal, GlobalBan, GuildConfig

logger = logging.getLogger(__name__)

# ────────── helpers de embed ──────────
class E:
    @staticmethod
    def _b(t, d, c):
        return discord.Embed(
            title=t, description=d, colour=c,
            timestamp=datetime.now(timezone.utc))
    ok   = staticmethod(lambda d, **k: E._b("✅ Sucesso", d, discord.Color.green()).set_footer(**k))
    err  = staticmethod(lambda d, **k: E._b("❌ Erro",    d, discord.Color.red())  .set_footer(**k))
    info = staticmethod(lambda d, **k: E._b("ℹ️ Informação", d, discord.Color.blue()).set_footer(**k))

# ────────── DB helper ──────────
@contextmanager
def db():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except:
        s.rollback()
        raise
    finally:
        s.close()

# ────────── check: quem é admin? ──────────
def is_admin(inter: discord.Interaction) -> bool:
    perms = inter.user.guild_permissions
    return perms.administrator

# ────────── Cog ──────────
class GlobalBanCog(commands.Cog):
    RATE_LIMIT  = 30         # s
    REASONS     = ["Spam", "Scam", "Tóxico", "NSFW", "Cheats", "Outro"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gban = 0.0
        self.log_channels: dict[int, Optional[int]] = {}
        self.ban_cache: set[int] = set()

        self.gban = app_commands.Group(name="gban", description="Comandos de ban global")
        self._register_slash()

    # ───── async hooks ─────
    async def cog_load(self):
        await self._cache_log_channels()
        await self._load_ban_cache()
        self.bot.tree.add_command(self.gban)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.gban.name, type=self.gban.type)

    # ───── cache ─────
    async def _cache_log_channels(self):
        with db() as s:
            self.log_channels = {
                int(cfg.guild_id): int(cfg.log_channel_id) if cfg.log_channel_id else None
                for cfg in s.query(GuildConfig)
            }

    async def _load_ban_cache(self):
        with db() as s:
            self.ban_cache = {int(r.discord_id) for r in s.query(GlobalBan.discord_id)}
        logger.info("[GlobalBan] cache %d IDs", len(self.ban_cache))

    # ───── logging util ─────
    async def _send_log(self, g: discord.Guild, embed: discord.Embed):
        ch = None
        ch_id = self.log_channels.get(g.id)
        if ch_id:
            ch = g.get_channel(ch_id)
        if ch is None:                        # fallback
            ch = g.system_channel
        if ch and ch.permissions_for(g.me).send_messages:
            await ch.send(embed=embed)

    async def _broadcast(self, emb: discord.Embed, guilds: List[discord.Guild]):
        await asyncio.gather(*(self._send_log(g, emb) for g in guilds))

    # ───── DB helpers ─────
    def _add_db(self, uid, by, reason):
        with db() as s:
            if s.query(GlobalBan.id).filter_by(discord_id=str(uid)).first():
                return False
            s.add(GlobalBan(discord_id=str(uid), banned_by=str(by), reason=reason))
            return True

    def _del_db(self, uid):
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
    async def _exec_ban(self, user, mod, reason):
        if time.time() - self.last_gban < self.RATE_LIMIT:
            raise RuntimeError(f"Aguarde {self.RATE_LIMIT}s entre bans.")

        ok, fail = await self._mass(
            self.bot.guilds, lambda g: g.ban(user, reason=f"[GlobalBan] {reason}")
        )
        if self._add_db(user.id, mod.id, reason):
            self.ban_cache.add(user.id)
        self.last_gban = time.time()

        try:                                   # tenta avisar por DM
            await user.send(embed=E.info(f"Você foi **banido globalmente**. Motivo: **{reason}**"))
        except discord.HTTPException:
            pass

        txt = (f"**Usuário:** {user} (`{user.id}`)\n"
               f"**Motivo:** {reason}\n"
               f"**Servidores banidos:** {len(ok)}/{len(self.bot.guilds)}")
        if fail:
            txt += f"\n⚠️ Falhou em: {', '.join(fail)}"
        emb = E.ok(txt, footer=f"Banido por {mod}", thumbnail_url=user.display_avatar.url)
        await self._broadcast(emb, ok)
        return emb

    async def _exec_unban(self, uid, mod):
        ok, fail = await self._mass(
            self.bot.guilds, lambda g: g.unban(discord.Object(id=uid), reason="[GlobalUnban]")
        )
        removed = self._del_db(uid); self.ban_cache.discard(uid)

        txt = (f"**Usuário ID:** `{uid}`\n"
               f"**Desbanido em:** {len(ok)}/{len(self.bot.guilds)} servidores\n"
               f"**Registros removidos:** {removed}")
        if fail:
            txt += f"\n⚠️ Falhou em: {', '.join(fail)}"
        emb = E.ok(txt, footer=f"Unban por {mod}")
        await self._broadcast(emb, ok)
        return emb

    # ───── prefix commands ─────
    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gban")
    async def gban_prefix(self, ctx, target: discord.User, *, reason="Sem Motivo"):
        try:
            emb = await self._exec_ban(target, ctx.author, reason)
        except RuntimeError as e:
            return await ctx.send(embed=E.err(str(e)))
        await ctx.send(embed=emb)

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="gunban")
    async def gunban_prefix(self, ctx, target_id: int):
        emb = await self._exec_unban(target_id, ctx.author)
        await ctx.send(embed=emb)

    # ───── slash registration ─────
    def _register_slash_commands(self):
        admin_chk = lambda i: i.user.guild_permissions.administrator

        # /gban add
        @self.gban.command(name="add", description="Ban global")
        @app_commands.check(admin_chk)
        @app_commands.describe(reason="Motivo do ban")
        @app_commands.choices(reason=[app_commands.Choice(name=n, value=n) for n in self.REASONS])
        async def _add(inter: discord.Interaction, target: discord.User, reason: str = "Sem Motivo"):
            await inter.response.defer(thinking=True)
            try:
                emb = await self._exec_ban(target, inter.user, reason)
            except RuntimeError as e:
                await inter.followup.send(embed=E.err(str(e)), ephemeral=True)
            else:
                await inter.followup.send(embed=emb)

        # /gban remove
        @self.gban.command(name="remove", description="Unban global")
        @app_commands.check(admin_chk)
        async def _remove(inter: discord.Interaction, target_id: int):
            await inter.response.defer(thinking=True)
            emb = await self._exec_unban(target_id, inter.user)
            await inter.followup.send(embed=emb)

        # /gban list
        @self.gban.command(name="list", description="Lista bans globais")
        @app_commands.check(admin_chk)
        async def _list(inter: discord.Interaction, page: int = 1):
            with db() as s:
                bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()
            if not bans:
                return await inter.response.send_message(
                    embed=E.info("Nenhum ban registrado."), ephemeral=True)

            PER = 10
            pages = (len(bans) + PER - 1) // PER
            page = max(1, min(page, pages))

            def make(idx: int):
                slice_ = bans[idx*PER:(idx+1)*PER]
                lines = [f"`{b.discord_id}` • {b.reason} • <t:{int(b.timestamp.timestamp())}:R>"
                         for b in slice_]
                return E.info("\n".join(lines), footer=f"Pág {idx+1}/{pages}")

            class Pager(discord.ui.View):
                def __init__(self, idx=page-1):
                    super().__init__(timeout=60); self.i = idx
                @discord.ui.button(label="◀️")
                async def prev(self, _, it):
                    if self.i > 0:
                        self.i -= 1
                        await it.response.edit_message(embed=make(self.i), view=self)
                @discord.ui.button(label="▶️")
                async def nxt(self, _, it):
                    if self.i < pages-1:
                        self.i += 1
                        await it.response.edit_message(embed=make(self.i), view=self)

            await inter.response.send_message(embed=make(page-1), view=Pager(), ephemeral=True)

        # /gban setlog
        @self.gban.command(name="setlog", description="Define canal de logs")
        @app_commands.check(lambda i: i.user.guild_permissions.manage_guild)
        async def _setlog(inter: discord.Interaction, channel: discord.TextChannel):
            with db() as s:
                cfg = s.merge(GuildConfig(guild_id=str(inter.guild.id)))
                cfg.log_channel_id = str(channel.id)
            self.log_channels[inter.guild.id] = channel.id
            await inter.response.send_message(
                embed=E.ok(f"Canal de logs definido para {channel.mention}."), ephemeral=True)

    # ───── global error handler (slash) ─────
    @commands.Cog.listener()
    async def on_app_command_error(self, inter: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await inter.response.send_message(
                embed=E.err("⚠️ Você não tem permissão para isso."),
                ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            await inter.response.send_message(
                embed=E.err("⚠️ Apenas administradores podem usar este comando."),
                ephemeral=True)
        else:
            logger.exception("Slash error", exc_info=error)
            if not inter.response.is_done():
                await inter.response.send_message(
                    embed=E.err(f"Erro inesperado: `{error.__class__.__name__}`"),
                    ephemeral=True)

# ────────── setup obrigatório ──────────
async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
