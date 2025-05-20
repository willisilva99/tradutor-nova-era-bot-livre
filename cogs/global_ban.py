import asyncio
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import List, Tuple, Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import SessionLocal, GlobalBan, GuildConfig  # suas tabelas

# ────────────────────── util embed ──────────────────────
class E:
    @staticmethod
    def _base(title, desc, color):  # helper interno
        return discord.Embed(
            title=title,
            description=desc,
            colour=color,
            timestamp=datetime.now(timezone.utc)
        )

    @staticmethod
    def ok(desc, **k):   return E._base("✅ Sucesso",     desc, discord.Color.green()).set_footer(**k)
    @staticmethod
    def err(desc, **k):  return E._base("❌ Erro",        desc, discord.Color.red()).set_footer(**k)
    @staticmethod
    def info(desc, **k): return E._base("ℹ️ Informação", desc, discord.Color.blue()).set_footer(**k)

# ────────────────────── session helper ──────────────────
@contextmanager
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# ────────────────────── main cog ────────────────────────
class GlobalBanCog(commands.GroupCog, name="gban"):
    OWNER_ID = 470628393272999948

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channels: dict[int, Optional[int]] = {}  # guild_id -> channel_id|None
        self._prepare_log_channel_cache()
        self.bot.loop.create_task(self._sync_ban_cache())

    # ------------- util -------------
    def _prepare_log_channel_cache(self):
        with db_session() as s:
            for cfg in s.query(GuildConfig).all():
                self.log_channels[int(cfg.guild_id)] = (
                    int(cfg.log_channel_id) if cfg.log_channel_id else None
                )

    async def _send_in_log(self, guild: discord.Guild, embed: discord.Embed):
        chan_id = self.log_channels.get(guild.id)
        channel  = guild.get_channel(chan_id) if chan_id else guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)

    async def _mass_action(
        self,
        guilds: List[discord.Guild],
        coro_factory,
    ) -> Tuple[List[discord.Guild], List[str]]:
        """
        Executa a coroutine (ban/unban) em paralelo.
        Retorna (sucesso, falha_nomes).
        """
        tasks = [coro_factory(g) for g in guilds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success, failed = [], []
        for g, res in zip(guilds, results):
            if isinstance(res, Exception):
                logging.exception("global ban error in %s", g.name)
                failed.append(g.name)
            else:
                success.append(g)
        return success, failed

    # ------------- DB helpers -------------
    def _add_ban_db(self, user_id: int, banner_id: int, reason: str):
        with db_session() as s:
            s.add(GlobalBan(
                discord_id=str(user_id),
                banned_by=str(banner_id),
                reason=reason,
                timestamp=datetime.now(timezone.utc)
            ))

    def _del_ban_db(self, user_id: int) -> int:
        with db_session() as s:
            return s.query(GlobalBan).filter_by(discord_id=str(user_id)).delete()

    async def _sync_ban_cache(self):
        """Auto-ban em todos os guilds caso o bot reinicie enquanto usuários banidos já estão neles."""
        await self.bot.wait_until_ready()
        with db_session() as s:
            banned_ids = {int(b.discord_id) for b in s.query(GlobalBan.discord_id).all()}
        for guild in self.bot.guilds:
            for m in guild.members:
                if m.id in banned_ids:
                    try:
                        await guild.ban(m, reason="[GlobalBan] Sincronização após restart")
                    except discord.Forbidden:
                        logging.warning("Sem permissão para re-banir %s em %s", m, guild)

    # ------------- eventos -------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Auto-ban se alguém na lista global entrar depois."""
        with db_session() as s:
            if not s.query(GlobalBan).filter_by(discord_id=str(member.id)).first():
                return

        try:
            await member.guild.ban(member, reason="[GlobalBan] Auto-ban on join")
            embed = E.ok(f"{member.mention} está globalmente banido e foi **banido automaticamente** deste servidor.")
            await self._send_in_log(member.guild, embed)
        except discord.Forbidden:
            pass

    # ============= comandos =============
    async def _exec_ban(
        self,
        interaction_or_ctx,
        target: discord.User,
        reason: str,
        dm_target: bool = True
    ):
        guilds          = self.bot.guilds
        coro_factory    = lambda g: g.ban(target, reason=f"[GlobalBan] {reason}")
        success, failed = await self._mass_action(guilds, coro_factory)

        self._add_ban_db(target.id, interaction_or_ctx.user.id, reason)

        desc = (
            f"**Usuário:** {target} (`{target.id}`)\n"
            f"**Motivo:** {reason}\n"
            f"**Servidores banidos:** {len(success)}/{len(guilds)}"
        )
        if failed: desc += f"\n⚠️ Falhou em: {', '.join(failed)}"

        embed = E.ok(desc, footer=f"Banido por {interaction_or_ctx.user}", thumbnail_url=target.display_avatar.url)

        # DM ao alvo?
        if dm_target:
            try:
                await target.send(embed=E.info(
                    f"Você foi **GLOBALMENTE BANIDO** por **{reason}**.",
                    thumbnail_url=interaction_or_ctx.guild.me.display_avatar.url
                ))
            except discord.Forbidden:
                pass

        await self._send_in_log(interaction_or_ctx.guild if isinstance(interaction_or_ctx, commands.Context) else interaction_or_ctx.guild, embed)
        await self.broadcast_embed(embed, success)
        return embed

    async def _exec_unban(self, interaction_or_ctx, target_id: int):
        guilds          = self.bot.guilds
        obj             = discord.Object(id=target_id)
        coro_factory    = lambda g: g.unban(obj, reason="[GlobalUnban]")
        success, failed = await self._mass_action(guilds, coro_factory)

        deleted = self._del_ban_db(target_id)

        desc = (
            f"**Usuário ID:** `{target_id}`\n"
            f"**Servidores desbanidos:** {len(success)}/{len(guilds)}\n"
            f"**Registros removidos:** {deleted}"
        )
        if failed: desc += f"\n⚠️ Falhou em: {', '.join(failed)}"

        embed = E.ok(desc, footer=f"Unban por {interaction_or_ctx.user}")
        await self._send_in_log(interaction_or_ctx.guild if isinstance(interaction_or_ctx, commands.Context) else interaction_or_ctx.guild, embed)
        await self.broadcast_embed(embed, success)
        return embed

    # prefix commands
    @commands.is_owner()
    @commands.command(name="gban")
    async def gban_prefix(self, ctx: commands.Context, target: discord.User, *, reason: str = "Sem Motivo"):
        embed = await self._exec_ban(ctx, target, reason)
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(name="gunban")
    async def gunban_prefix(self, ctx: commands.Context, target_id: int):
        embed = await self._exec_unban(ctx, target_id)
        await ctx.send(embed=embed)

    # slash group
    @app_commands.guild_only()
    class Gban(app_commands.Group, name="gban", description="Comandos de ban global"):
        pass

    @Gban.command(name="add", description="Ban global")
    @app_commands.checks.is_owner()
    async def _gban_add(self, inter: discord.Interaction, target: discord.User, reason: str = "Sem Motivo"):
        await inter.response.defer(thinking=True)
        embed = await self._exec_ban(inter, target, reason)
        await inter.followup.send(embed=embed)

    @Gban.command(name="remove", description="Unban global")
    @app_commands.checks.is_owner()
    async def _gban_remove(self, inter: discord.Interaction, target_id: int):
        await inter.response.defer(thinking=True)
        embed = await self._exec_unban(inter, target_id)
        await inter.followup.send(embed=embed)

    @Gban.command(name="list", description="Mostra usuários banidos globalmente")
    @app_commands.checks.is_owner()
    async def _gban_list(self, inter: discord.Interaction, page: int = 1):
        with db_session() as s:
            bans = s.query(GlobalBan).order_by(GlobalBan.timestamp.desc()).all()

        if not bans:
            return await inter.response.send_message(embed=E.info("Nenhum ban global registrado."), ephemeral=True)

        per_page = 10
        pages    = (len(bans) + per_page - 1) // per_page
        page     = max(1, min(page, pages))
        start    = (page - 1) * per_page
        chunk    = bans[start:start+per_page]

        lines = [
            f"`{b.discord_id}` • {b.reason} • <t:{int(b.timestamp.timestamp())}:R>"
            for b in chunk
        ]
        embed = E.info("\n".join(lines), footer=f"Pág {page}/{pages}")
        await inter.response.send_message(embed=embed, ephemeral=True)

    # error handler
    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(embed=E.err("Somente o dono do bot pode usar este comando."))
        else:
            logger.exception("Erro no GlobalBan cog")
            await ctx.send(embed=E.err(f"Erro inesperado: {error}"))

    # helper para broadcast
    async def broadcast_embed(self, embed: discord.Embed, guilds: List[discord.Guild]):
        for g in guilds:
            await self._send_in_log(g, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalBanCog(bot))
