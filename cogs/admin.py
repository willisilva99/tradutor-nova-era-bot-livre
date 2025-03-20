import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import timedelta, datetime

class AdminCog(commands.Cog):
    """Comandos administrativos avançados, incluindo mute, kick, warn, slowmode, logs, proteção contra palavrões e muito mais."""

    def __init__(self, bot):
        self.bot = bot
        
        # Sistema de banimentos temporários
        self.banned_users = {}  # {guild_id: {user_id: datetime_unban}}
        self.tempban_task.start()
        
        # Sistema de avisos
        self.warns = {}  # {user_id: quantidade_de_warns}
        
        # Configuração inicial do anti-swear
        self.anti_swear_active = True
        
        # Lista de palavras proibidas (exemplo básico)
        self.blocked_words = ["palavrão1", "palavrão2", "palavrão3"]

    # ============== Tarefa agendada para remover banimentos temporários ==============

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
    
    # ============== Verificação de Permissões ==============

    async def check_permissions(self, interaction: discord.Interaction, permission: str):
        """
        Checa se o autor do comando possui a permissão necessária.
        Exemplo de permissão: 'ban_members', 'kick_members', 'manage_messages', etc.
        """
        if not getattr(interaction.user.guild_permissions, permission, False):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Acesso Negado",
                    description="Você não tem permissão para executar este comando!",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True

    # ============== Sistema de Logs ==============

    async def log_action(self, interaction: discord.Interaction, action: str, user: discord.Member, reason: str):
        """
        Registra a ação de moderação em um canal de logs chamado 'logs'.
        Se quiser, pode trocar o nome do canal ou buscar pelo ID.
        """
        log_channel = discord.utils.get(interaction.guild.channels, name="logs")
        if log_channel:
            embed = discord.Embed(
                title=f"📜 Ação de Moderação: {action}",
                description=(
                    f"👤 **Usuário**: {user.mention}\n"
                    f"✏️ **Motivo**: {reason}\n"
                    f"👮 **Moderador**: {interaction.user.mention}\n"
                    f"📅 **Data**: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                ),
                color=discord.Color.blue()
            )
            await log_channel.send(embed=embed)

    # ============== Comandos de Banimento ==============

    @app_commands.command(name="tempban", description="⏳ Bane temporariamente um usuário.")
    async def tempban(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Não especificado"):
        """Bane o usuário por X minutos."""
        if not await self.check_permissions(interaction, "ban_members"):
            return
        
        unban_time = datetime.utcnow() + timedelta(minutes=duration)
        self.banned_users.setdefault(interaction.guild.id, {})[user.id] = unban_time

        await interaction.guild.ban(user, reason=reason)
        await self.log_action(interaction, "Ban Temporário", user, reason)
        
        embed = discord.Embed(
            title="⏳ Ban Temporário",
            description=f"**{user.mention} foi banido por {duration} minutos.**",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ban", description="🚫 Bane permanentemente um usuário.")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "ban_members"):
            return
        
        await interaction.guild.ban(user, reason=reason)
        await self.log_action(interaction, "Ban Permanente", user, reason)
        
        embed = discord.Embed(
            title="🚫 Ban Permanente",
            description=f"**{user.mention} foi banido permanentemente.**",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    # ============== Comando Kick ==============

    @app_commands.command(name="kick", description="👟 Expulsa um usuário do servidor.")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "kick_members"):
            return
        
        await user.kick(reason=reason)
        await self.log_action(interaction, "Kick", user, reason)
        
        embed = discord.Embed(
            title="👟 Kick",
            description=f"**{user.mention} foi expulso do servidor.**",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)

    # ============== Comando Mute ==============

    @app_commands.command(name="mute", description="🔇 Silencia um usuário por X minutos.")
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration: int = 0, reason: str = "Não especificado"):
        """
        Se 'duration' for 0, muta permanentemente até que seja desmutado.
        É necessário ter um papel chamado 'Mutado' ou criar dinamicamente.
        """
        if not await self.check_permissions(interaction, "manage_roles"):
            return

        # Procura (ou cria) role de Mutado:
        muted_role = discord.utils.get(interaction.guild.roles, name="Mutado")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Mutado", reason="Criando papel para Mute.")
                for channel in interaction.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Não foi possível criar/adicionar o papel 'Mutado'. Erro: {e}",
                    ephemeral=True
                )
                return
        
        await user.add_roles(muted_role, reason=reason)

        await self.log_action(interaction, "Mute", user, reason)
        
        if duration > 0:
            embed = discord.Embed(
                title="🔇 Mute Temporário",
                description=f"**{user.mention} foi silenciado por {duration} minutos.**",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)

            # Desmuta automaticamente após X minutos
            await self.unmute_after_delay(interaction.guild, user, duration, reason)
        else:
            embed = discord.Embed(
                title="🔇 Mute",
                description=f"**{user.mention} foi silenciado por tempo indeterminado.**",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)

    async def unmute_after_delay(self, guild: discord.Guild, user: discord.Member, duration: int, reason: str):
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=duration))
        muted_role = discord.utils.get(guild.roles, name="Mutado")
        if muted_role in user.roles:
            await user.remove_roles(muted_role, reason="Mute expirado")
            # Caso queira logar:
            channel = discord.utils.get(guild.text_channels, name="logs")
            if channel:
                embed = discord.Embed(
                    title="🔊 Desmute automático",
                    description=f"**{user.mention} foi desmutado após {duration} minutos.**",
                    color=discord.Color.green()
                )
                await channel.send(embed=embed)

    # ============== Comando Unmute ==============

    @app_commands.command(name="unmute", description="🔊 Remove o mute de um usuário.")
    async def unmute(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_roles"):
            return
        
        muted_role = discord.utils.get(interaction.guild.roles, name="Mutado")
        if muted_role in user.roles:
            await user.remove_roles(muted_role, reason=reason)
            await self.log_action(interaction, "Unmute", user, reason)
            
            embed = discord.Embed(
                title="🔊 Unmute",
                description=f"**{user.mention} foi desmutado.**",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"**{user.mention} não está mutado.**", ephemeral=True)

    # ============== Comando Warn ==============

    @app_commands.command(name="warn", description="⚠️ Envia um aviso a um usuário.")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_messages"):
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        self.warns.setdefault(user.id, 0)
        self.warns[user.id] += 1
        
        current_warns = self.warns[user.id]
        
        # Ações automáticas dependendo da contagem de warns
        if current_warns == 3:
            # Exemplo: Mute de 10 minutos
            await self.mute(interaction, user, 10, "3 avisos acumulados")
        elif current_warns == 5:
            # Exemplo: Kick
            await self.kick(interaction, user, "5 avisos acumulados")
        elif current_warns == 7:
            # Exemplo: Ban
            await self.ban(interaction, user, "7 avisos acumulados - ban permanente")

        await self.log_action(interaction, "Aviso", user, reason)
        
        embed = discord.Embed(
            title="⚠️ Usuário Avisado",
            description=f"**{user.mention} recebeu um aviso!** (Total: {current_warns})",
            color=discord.Color.orange()
        )
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ O usuário foi avisado.", ephemeral=True)

    # ============== Comando para Listar Warns ==============

    @app_commands.command(name="listwarns", description="Lista quantos warns um usuário possui.")
    async def list_warns(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.check_permissions(interaction, "manage_messages"):
            return

        warns_count = self.warns.get(user.id, 0)
        embed = discord.Embed(
            title="⚠️ Contagem de Avisos",
            description=f"O usuário {user.mention} possui **{warns_count}** avisos.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============== Comando para Remover Warns ==============

    @app_commands.command(name="clearwarns", description="Remove todos os warns de um usuário.")
    async def clear_warns(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.check_permissions(interaction, "manage_messages"):
            return
        
        if user.id in self.warns:
            del self.warns[user.id]
        
        embed = discord.Embed(
            title="⚠️ Avisos Removidos",
            description=f"Todos os avisos de {user.mention} foram removidos.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============== Comando Slowmode ==============

    @app_commands.command(name="slowmode", description="Define o modo lento em segundos em um canal.")
    async def slowmode(self, interaction: discord.Interaction, segundos: int):
        if not await self.check_permissions(interaction, "manage_channels"):
            return
        
        await interaction.channel.edit(slowmode_delay=segundos)
        embed = discord.Embed(
            title="⌛ Slowmode",
            description=f"Modo lento ajustado para {segundos} segundos neste canal.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    # ============== Comandos de Lock e Unlock do Canal ==============

    @app_commands.command(name="lockchannel", description="Tranca o canal para que ninguém possa enviar mensagens.")
    async def lock_channel(self, interaction: discord.Interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"):
            return
        
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        await self.log_action(interaction, "LockChannel", interaction.user, reason)
        
        embed = discord.Embed(
            title="🔒 Canal Trancado",
            description=f"**{interaction.channel.mention} foi trancado.**",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlockchannel", description="Destranca o canal para que todos possam enviar mensagens.")
    async def unlock_channel(self, interaction: discord.Interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"):
            return
        
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = True
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        await self.log_action(interaction, "UnlockChannel", interaction.user, reason)
        
        embed = discord.Embed(
            title="🔓 Canal Destrancado",
            description=f"**{interaction.channel.mention} foi destrancado.**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ============== Comando Clear (Purge) ==============
    
    @app_commands.command(name="clear", description="Limpa um número específico de mensagens do canal.")
    async def clear_messages(self, interaction: discord.Interaction, quantidade: int):
        if not await self.check_permissions(interaction, "manage_messages"):
            return
        
        await interaction.channel.purge(limit=quantidade+1)  # +1 para remover também o comando do usuário
        embed = discord.Embed(
            title="🧹 Limpeza de Mensagens",
            description=f"Foram deletadas **{quantidade}** mensagens neste canal.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============== Anti-Swear (Listener) ==============
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.anti_swear_active:
            # Ignora se a mensagem foi enviada por um bot ou no DM
            if message.author.bot or not message.guild:
                return
            
            # Verifica se alguma palavra proibida está na mensagem
            msg_lower = message.content.lower()
            for word in self.blocked_words:
                if word in msg_lower:
                    try:
                        await message.delete()
                        # Ação opcional: adicionar warn ou logar
                        channel = discord.utils.get(message.guild.channels, name="logs")
                        if channel:
                            embed = discord.Embed(
                                title="⚠️ Anti-Swear",
                                description=(
                                    f"Mensagem deletada de {message.author.mention}\n"
                                    f"**Conteúdo:** {message.content}"
                                ),
                                color=discord.Color.red()
                            )
                            await channel.send(embed=embed)
                    except:
                        pass
                    finally:
                        break  # Sai do loop para não contar várias vezes se tiver várias palavras

    @app_commands.command(name="toggleswear", description="Ativa ou desativa a filtragem de palavrões.")
    async def toggle_swear(self, interaction: discord.Interaction):
        if not await self.check_permissions(interaction, "manage_messages"):
            return
        
        self.anti_swear_active = not self.anti_swear_active
        status = "ativada" if self.anti_swear_active else "desativada"
        embed = discord.Embed(
            title="🛡️ Anti-Swear",
            description=f"A proteção contra palavrões foi **{status}**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ============== Setup ==============

    async def cog_unload(self):
        self.tempban_task.cancel()

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
