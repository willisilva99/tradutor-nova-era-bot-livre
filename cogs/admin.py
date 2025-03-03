import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import timedelta, datetime
import asyncio

class AdminCog(commands.Cog):
    """Comandos administrativos avançados incluindo mute, kick, warn, slowmode, logs e proteção contra palavrões."""

    def __init__(self, bot):
        self.bot = bot
        self.banned_users = {}
        self.anti_swear_active = True  # Configuração inicial para ativar/desativar
        self.warns = {}  # Sistema de avisos com acúmulo
        self.tempban_task.start()

    @tasks.loop(minutes=1)
    async def tempban_task(self):
        """Verifica se há usuários a serem desbanidos."""
        now = datetime.utcnow()
        for guild_id, bans in list(self.banned_users.items()):
            for user_id, unban_time in list(bans.items()):
                if now >= unban_time:
                    guild = self.bot.get_guild(guild_id)
                    user = await self.bot.fetch_user(user_id)
                    if guild and user:
                        await guild.unban(user, reason="Ban temporário expirado")
                        del self.banned_users[guild_id][user_id]

    async def check_permissions(self, interaction: discord.Interaction, permission: str):
        if not getattr(interaction.user.guild_permissions, permission, False):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Acesso Negado",
                    description="Você não tem permissão para executar este comando!",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            await interaction.message.add_reaction("❌")
            return False
        return True

    async def log_action(self, interaction: discord.Interaction, action: str, user: discord.Member, reason: str):
        log_channel = discord.utils.get(interaction.guild.channels, name="logs")
        if log_channel:
            embed = discord.Embed(
                title=f"📜 Ação de Moderação: {action}",
                description=f"👤 **Usuário**: {user.mention}\n✏️ **Motivo**: {reason}\n👮 **Moderador**: {interaction.user.mention}\n📅 **Data**: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            await log_channel.send(embed=embed)

    @app_commands.command(name="tempban", description="⏳ Bane temporariamente um usuário.")
    async def tempban(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "ban_members"):
            return
        
        unban_time = datetime.utcnow() + timedelta(minutes=duration)
        if interaction.guild.id not in self.banned_users:
            self.banned_users[interaction.guild.id] = {}
        self.banned_users[interaction.guild.id][user.id] = unban_time

        await interaction.guild.ban(user, reason=reason)
        await self.log_action(interaction, "Ban Temporário", user, reason)
        embed = discord.Embed(title="⏳ Ban Temporário", description=f"**{user.mention} foi banido por {duration} minutos.**", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warn", description="⚠️ Envia um aviso a um usuário.")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_messages"):
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        if user.id not in self.warns:
            self.warns[user.id] = 0
        self.warns[user.id] += 1

        if self.warns[user.id] == 3:
            await self.mute(interaction, user, 10, "3 avisos acumulados")
        elif self.warns[user.id] == 5:
            await self.kick(interaction, user, "5 avisos acumulados")
        elif self.warns[user.id] == 7:
            await self.tempban(interaction, user, 1440, "7 avisos acumulados - ban permanente")

        await self.log_action(interaction, "Aviso", user, reason)
        embed = discord.Embed(title="⚠️ Usuário Avisado", description=f"**{user.mention} recebeu um aviso!** (Total: {self.warns[user.id]})", color=discord.Color.orange())
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ O usuário foi avisado.", ephemeral=True)

    @app_commands.command(name="userinfo", description="🔍 Mostra informações sobre um usuário.")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member):
        embed = discord.Embed(title=f"🔍 Informações de {user.name}", color=discord.Color.blue())
        embed.add_field(name="🆔 ID", value=user.id, inline=True)
        embed.add_field(name="📅 Entrou no servidor", value=user.joined_at.strftime('%d/%m/%Y'), inline=True)
        embed.add_field(name="🚀 Cargos", value=", ".join([role.name for role in user.roles if role.name != "@everyone"]) or "Nenhum", inline=False)
        embed.add_field(name="⚠️ Avisos", value=str(self.warns.get(user.id, 0)), inline=True)
        embed.set_thumbnail(url=user.avatar.url)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.anti_swear_active and any(word in message.content.lower() for word in ["palavrão1", "palavrão2"]):
            await message.delete()
            await message.channel.send(f"🚫 {message.author.mention}, palavrões não são permitidos!", delete_after=5)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
