import re
import json
import os
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class EmbedFactory:
    """Fábrica para criar embeds padronizados, ricos e reutilizáveis."""
    @staticmethod
    def base(title, description, color=discord.Color.blurple(), icon_url=None, footer=None, thumbnail_url=None):
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
        if icon_url:
            embed.set_author(name=title, icon_url=icon_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @staticmethod
    def success(description, title="✔️ Sucesso", **kwargs):
        return EmbedFactory.base(title, description, color=discord.Color.green(), **kwargs)

    @staticmethod
    def error(description, title="❌ Erro", **kwargs):
        return EmbedFactory.base(title, description, color=discord.Color.red(), **kwargs)

    @staticmethod
    def info(description, title="ℹ️ Informação", **kwargs):
        return EmbedFactory.base(title, description, color=discord.Color.blue(), **kwargs)


class AdminCog(commands.Cog):
    """
    Comandos administrativos avançados e utilitários:
    ban/kick/tempban/unban, purge, slowmode, lockdown, role/nick management,
    server/user info, anti-swear com auto-warns e muito mais.
    """

    STATE_FILE = "admin_state.json"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.banned_users = {}   # {guild_id: {user_id: unban_datetime}}
        self.warns = {}          # {guild_id: {user_id: warn_count}}
        self.anti_swear_active = True
        self.blocked_words = [
            "porra", "caralho", "merda", "puta", "cacete", "fodase", "foda-se",
            "filhodaputa", "filho da puta", "vai se foder", "vai te catar",
            "viado", "bicha", "traveco", "tchola",
            "macaco", "negro de merda", "crioulada",
            "sua mãe", "sua avó", "seu pai", "seu irmão",
            "idiota", "burro", "retardado", "imbecil", "otário"
        ]
        self.blocked_patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in self.blocked_words]

        self.load_state()
        self.tempban_task.start()

    def cog_unload(self):
        self.tempban_task.cancel()
        self.save_state()

    @tasks.loop(minutes=1)
    async def tempban_task(self):
        now = datetime.now(timezone.utc)
        for guild_id, bans in list(self.banned_users.items()):
            for user_id, unban_time in list(bans.items()):
                if now >= unban_time:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        try:
                            await guild.unban(discord.Object(id=user_id), reason="Ban temporário expirado")
                        except Exception:
                            logger.exception("Falha ao desbanir temporário")
                    del self.banned_users[guild_id][user_id]
        self.save_state()

    def save_state(self):
        data = {
            "banned_users": {
                str(g): {str(u): dt.timestamp() for u, dt in bans.items()}
                for g, bans in self.banned_users.items()
            },
            "warns": {
                str(g): uw for g, uw in self.warns.items()
            }
        }
        with open(self.STATE_FILE, "w") as f:
            json.dump(data, f)

    def load_state(self):
        if not os.path.isfile(self.STATE_FILE):
            return
        with open(self.STATE_FILE, "r") as f:
            data = json.load(f)
        self.banned_users = {
            int(g): {int(u): datetime.fromtimestamp(ts, timezone.utc) for u, ts in bans.items()}
            for g, bans in data.get("banned_users", {}).items()
        }
        self.warns = {
            int(g): {int(u): c for u, c in uw.items()}
            for g, uw in data.get("warns", {}).items()
        }

    async def check_permissions(self, interaction, perm: str):
        if not getattr(interaction.user.guild_permissions, perm, False):
            embed = EmbedFactory.error("Você não tem permissão para executar este comando!", footer="Permissões")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def log_action(self, interaction, action: str, user, reason: str, extra: str = ""):
        channel = discord.utils.get(interaction.guild.channels, name="logs")
        if not channel:
            return
        embed = EmbedFactory.info(
            f"👤 **Usuário**: {user.mention}\n"
            f"🔍 **Motivo**: {reason}\n"
            f"{extra}",
            title=f"📜 {action}",
            footer=f"{interaction.guild.name} • {datetime.now():%d/%m/%Y %H:%M}"
        )
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = EmbedFactory.error("Você não tem permissão para este comando.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = EmbedFactory.error(f"Ocorreu um erro: `{error}`")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.exception(f"Erro em comando {interaction.command}: {error}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not self.anti_swear_active:
            return
        for patt in self.blocked_patterns:
            if patt.search(message.content):
                try:
                    await message.delete()
                except discord.Forbidden:
                    return
                gid, uid = message.guild.id, message.author.id
                self.warns.setdefault(gid, {})
                count = self.warns[gid].get(uid, 0) + 1
                self.warns[gid][uid] = count
                self.save_state()
                await message.channel.send(f"⚠️ {message.author.mention}, você recebeu **{count}/3** avisos.")
                if count >= 3:
                    try:
                        await message.guild.kick(message.author, reason="3 avisos de palavrões")
                        del self.warns[gid][uid]
                        self.save_state()
                        await message.channel.send(f"👢 {message.author.mention} foi expulso após 3 avisos.")
                    except discord.Forbidden:
                        await message.channel.send(f"❌ Sem permissão para expulsar {message.author.mention}.")
                return

    # ─────────────────────────────────────────────────────────────────────────
    #                        COMANDOS DE MODERAÇÃO
    # ─────────────────────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="🚫 Bane permanentemente um usuário.")
    @app_commands.describe(user="Usuário", reason="Motivo")
    async def ban(self, interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "ban_members"): return
        await interaction.guild.ban(user, reason=reason)
        await self.log_action(interaction, "Ban Permanente", user, reason)
        embed = EmbedFactory.success(f"{user.mention} banido. Motivo: {reason}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tempban", description="⏳ Ban temporário (minutos).")
    @app_commands.describe(user="Usuário", duration="Minutos", reason="Motivo")
    async def tempban(self, interaction, user: discord.Member, duration: int, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "ban_members"): return
        when = datetime.now(timezone.utc) + timedelta(minutes=duration)
        self.banned_users.setdefault(interaction.guild.id, {})[user.id] = when
        await interaction.guild.ban(user, reason=reason)
        self.save_state()
        await self.log_action(interaction, "Ban Temporário", user, f"{reason} (por {duration}min)")
        embed = EmbedFactory.success(f"{user.mention} banido por {duration}min. Motivo: {reason}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unban", description="♻️ Desbane um usuário pelo ID.")
    @app_commands.describe(user_id="ID do usuário")
    async def unban(self, interaction, user_id: str):
        if not await self.check_permissions(interaction, "ban_members"): return
        try:
            await interaction.guild.unban(discord.Object(id=int(user_id)))
            embed = EmbedFactory.success(f"Usuário `{user_id}` desbanido.")
        except Exception:
            embed = EmbedFactory.error(f"Não foi possível desbanir `{user_id}`.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="banlist", description="📜 Lista de bans ativos.")
    async def banlist(self, interaction):
        if not await self.check_permissions(interaction, "ban_members"): return
        bans = await interaction.guild.bans()
        desc = "\n".join(f"{b.user} - {b.reason or 'Sem motivo'}" for b in bans) or "Nenhum ban ativo."
        embed = EmbedFactory.info(desc, title="🛑 Bans Ativos")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="👟 Expulsa um usuário.")
    @app_commands.describe(user="Usuário", reason="Motivo")
    async def kick(self, interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "kick_members"): return
        await user.kick(reason=reason)
        await self.log_action(interaction, "Kick", user, reason)
        embed = EmbedFactory.success(f"{user.mention} expulso. Motivo: {reason}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="🧹 Remove N mensagens.")
    @app_commands.describe(amount="Quantidade", reason="Motivo (opcional)")
    async def purge(self, interaction, amount: int, reason: str = None):
        if not await self.check_permissions(interaction, "manage_messages"): return
        deleted = await interaction.channel.purge(limit=amount+1)
        text = f"{len(deleted)-1} mensagens removidas."
        if reason: text += f" Motivo: {reason}"
        embed = EmbedFactory.success(text)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="slowmode", description="⌛ Define slowmode (segundos).")
    @app_commands.describe(seconds="Segundos")
    async def slowmode(self, interaction, seconds: int):
        if not await self.check_permissions(interaction, "manage_channels"): return
        await interaction.channel.edit(slowmode_delay=seconds)
        embed = EmbedFactory.success(f"Slowmode definido para {seconds}s neste canal.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lock", description="🔒 Tranca o canal.")
    @app_commands.describe(reason="Motivo")
    async def lock(self, interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"): return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        embed = EmbedFactory.success(f"Canal trancado. Motivo: {reason}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlock", description="🔓 Destranca o canal.")
    @app_commands.describe(reason="Motivo")
    async def unlock(self, interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"): return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
        embed = EmbedFactory.success(f"Canal destrancado. Motivo: {reason}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setnick", description="✏️ Altera nickname de um usuário.")
    @app_commands.describe(user="Usuário", nickname="Novo nickname")
    async def setnick(self, interaction, user: discord.Member, nickname: str):
        if not await self.check_permissions(interaction, "manage_nicknames"): return
        await user.edit(nick=nickname)
        embed = EmbedFactory.success(f"{user.mention} agora é **{nickname}**.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="role", description="⚙️ Adiciona ou remove um cargo.")
    @app_commands.describe(action="add ou remove", user="Usuário", role="Cargo")
    async def role(self, interaction, action: str, user: discord.Member, role: discord.Role):
        if not await self.check_permissions(interaction, "manage_roles"): return
        if action.lower() == "add":
            await user.add_roles(role)
            embed = EmbedFactory.success(f"{role.mention} adicionado a {user.mention}.")
        else:
            await user.remove_roles(role)
            embed = EmbedFactory.success(f"{role.mention} removido de {user.mention}.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="🏷️ Informações do servidor.")
    async def serverinfo(self, interaction):
        guild = interaction.guild
        desc = (
            f"📅 Criado em: {guild.created_at:%d/%m/%Y}\n"
            f"👑 Dono: {guild.owner}\n"
            f"👥 Membros: {guild.member_count}\n"
            f"📝 Canais: {len(guild.channels)}\n"
            f"🏷️ Cargos: {len(guild.roles)}"
        )
        embed = EmbedFactory.info(desc, title=f"📋 {guild.name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="ℹ️ Informações de um usuário.")
    @app_commands.describe(user="Usuário")
    async def userinfo(self, interaction, user: discord.Member):
        desc = (
            f"🆔 ID: {user.id}\n"
            f"📅 Entrou: {user.joined_at:%d/%m/%Y}\n"
            f"🏷️ Cargos: {', '.join(r.name for r in user.roles[1:]) or 'Nenhum'}"
        )
        embed = EmbedFactory.info(desc, title=f"👤 {user}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
