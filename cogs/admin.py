import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta

class AdminCog(commands.Cog):
    """Comandos administrativos como mute, unmute, kick, ban, warn e slowmode."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mute", description="🔇 Silencia um usuário por um tempo definido.")
    @app_commands.describe(user="Usuário a ser silenciado", duration="Duração em minutos (1-1440)", reason="Motivo do mute")
    @app_commands.checks.has_permissions(moderate_members=True, manage_roles=True)
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Não especificado"):
        if duration < 1 or duration > 1440:
            return await interaction.response.send_message("⏳ **Duração deve estar entre 1 e 1440 minutos!**", ephemeral=True)
        try:
            await user.timeout(timedelta(minutes=duration), reason=reason)
            embed = discord.Embed(title="🔇 Usuário Silenciado", description=f"**{user.mention} foi silenciado por {duration} minutos.**", color=discord.Color.orange())
            embed.add_field(name="Motivo", value=reason, inline=False)
            embed.set_footer(text=f"Silenciado por {interaction.user}", icon_url=interaction.user.avatar.url)
            await interaction.response.send_message(embed=embed)
            await interaction.channel.send(f"🔇 {user.mention} foi silenciado por {duration} minutos.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ **Não tenho permissão para silenciar este usuário!**", ephemeral=True)

    @app_commands.command(name="unmute", description="🔊 Remove o silêncio de um usuário.")
    @app_commands.describe(user="Usuário a ser desmutado")
    @app_commands.checks.has_permissions(moderate_members=True, manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        try:
            await user.timeout(None)
            embed = discord.Embed(title="🔊 Usuário Desmutado", description=f"**{user.mention} pode falar novamente!**", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
            await interaction.channel.send(f"🔊 {user.mention} foi desmutado.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ **Não tenho permissão para desmutar este usuário!**", ephemeral=True)

    @app_commands.command(name="kick", description="🚪 Expulsa um usuário do servidor.")
    @app_commands.describe(user="Usuário a ser expulso", reason="Motivo do kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        try:
            await user.kick(reason=reason)
            embed = discord.Embed(title="🚪 Usuário Expulso", description=f"**{user.mention} foi expulso do servidor!**", color=discord.Color.red())
            embed.add_field(name="Motivo", value=reason, inline=False)
            embed.set_footer(text=f"Expulso por {interaction.user}", icon_url=interaction.user.avatar.url)
            await interaction.response.send_message(embed=embed)
            await interaction.channel.send(f"🚪 {user.mention} foi expulso do servidor! 🛑")
        except discord.Forbidden:
            await interaction.response.send_message("❌ **Não tenho permissão para expulsar este usuário!**", ephemeral=True)

    @app_commands.command(name="warn", description="⚠️ Envia um aviso a um usuário.")
    @app_commands.describe(user="Usuário a ser avisado", reason="Motivo do aviso")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        embed = discord.Embed(title="⚠️ Aviso de Moderação", description=f"**{user.mention}, você recebeu um aviso!**", color=discord.Color.orange())
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.set_footer(text=f"Aviso enviado por {interaction.user}", icon_url=interaction.user.avatar.url)
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ **Usuário desativou mensagens diretas, aviso não enviado!**", ephemeral=True)
        await interaction.response.send_message(embed=embed)
        await interaction.channel.send(f"⚠️ {user.mention} recebeu um aviso! 🚨")

    @app_commands.command(name="slowmode", description="⏳ Define um tempo entre mensagens no canal atual.")
    @app_commands.describe(seconds="Tempo entre mensagens em segundos (0 para desativar)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0 or seconds > 21600:
            return await interaction.response.send_message("⏳ **Escolha um valor entre 0 e 21600 segundos!**", ephemeral=True)
        await interaction.channel.edit(slowmode_delay=seconds)
        embed = discord.Embed(title="⏳ Modo Lento", description=f"**Agora os usuários devem esperar {seconds} segundos entre cada mensagem!**" if seconds > 0 else "📢 **Modo lento desativado!**", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
