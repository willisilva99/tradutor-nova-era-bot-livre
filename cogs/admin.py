import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta

class AdminCog(commands.Cog):
    """Comandos administrativos como mute, unmute, kick, ban, warn e slowmode."""

    def __init__(self, bot):
        self.bot = bot

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

    @app_commands.command(name="mute", description="🔇 Silencia um usuário por um tempo definido.")
    @app_commands.describe(user="Usuário a ser silenciado", duration="Duração em minutos (1-1440)", reason="Motivo do mute")
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "moderate_members"):
            return
        
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

    @app_commands.command(name="warn", description="⚠️ Envia um aviso a um usuário.")
    @app_commands.describe(user="Usuário a ser avisado", reason="Motivo do aviso")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_messages"):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        embed = discord.Embed(
            title="⚠️ Aviso de Moderação",
            description=f"**{user.mention}, você recebeu um aviso!**",
            color=discord.Color.orange()
        )
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.set_footer(text=f"Aviso enviado por {interaction.user}", icon_url=interaction.user.avatar.url)
        
        dm_sent = True
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            dm_sent = False
        
        public_embed = discord.Embed(
            title="⚠️ Usuário Avisado",
            description=f"**{user.mention} recebeu um aviso!**",
            color=discord.Color.orange()
        )
        public_embed.add_field(name="Motivo", value=reason, inline=False)
        public_embed.set_footer(text=f"Ação realizada por {interaction.user}", icon_url=interaction.user.avatar.url)
        
        await interaction.channel.send(embed=public_embed)
        
        if dm_sent:
            await interaction.followup.send("✅ O usuário foi avisado via DM.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ O usuário bloqueou DMs. Aviso enviado apenas no canal.", ephemeral=True)

    @app_commands.command(name="slowmode", description="⏳ Define um tempo entre mensagens no canal atual.")
    @app_commands.describe(seconds="Tempo entre mensagens em segundos (0 para desativar)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not await self.check_permissions(interaction, "manage_channels"):
            return
        
        if seconds < 0 or seconds > 21600:
            return await interaction.response.send_message("⏳ **Escolha um valor entre 0 e 21600 segundos!**", ephemeral=True)
        
        await interaction.channel.edit(slowmode_delay=seconds)
        embed = discord.Embed(title="⏳ Modo Lento", description=f"**Agora os usuários devem esperar {seconds} segundos entre cada mensagem!**" if seconds > 0 else "📢 **Modo lento desativado!**", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
