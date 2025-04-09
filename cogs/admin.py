import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import timedelta, datetime

class AdminCog(commands.Cog):
    """
    Comandos administrativos avançados, incluindo mute, kick, warn, slowmode, logs,
    proteção contra palavrões e muito mais.
    """
    def __init__(self, bot):
        self.bot = bot

        # ===================== Banimento Temporário =====================
        self.banned_users = {}  # {guild_id: {user_id: datetime_unban}}
        self.tempban_task.start()

        # ===================== Sistema de Avisos (Warns) =====================
        self.warns = {}  # {user_id: quantidade_de_warns}

        # ===================== Anti-Swear (Básico) =====================
        self.anti_swear_active = True
        self.blocked_words = ["palavrão1", "palavrão2", "palavrão3"]

    # ==========================================================
    #                       TAREFA AGENDADA
    # ==========================================================
    @tasks.loop(minutes=1)
    async def tempban_task(self):
        """Verifica se há usuários a serem desbanidos (ban temporário)."""
        now = datetime.utcnow()
        for guild_id, bans in list(self.banned_users.items()):
            for user_id, unban_time in list(bans.items()):
                if now >= unban_time:
                    guild = self.bot.get_guild(guild_id)
                    user = await self.bot.fetch_user(user_id)
                    if guild and user:
                        await guild.unban(user, reason="Ban temporário expirado")
                        del self.banned_users[guild_id][user_id]

    # ==========================================================
    #              LISTENER PARA ERROS DE SLASH
    # ==========================================================
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        """
        Se um usuário tentar usar comandos que exigem permissões e não tiver,
        ou qualquer outro erro, tratamos aqui para exibir mensagens amigáveis.
        """
        if isinstance(error, app_commands.MissingPermissions):
            # Usuário sem permissão
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Acesso Negado",
                    description="Você não tem permissão para executar este comando!",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        else:
            # Outros erros que não sejam MissingPermissions
            # Você pode personalizar ou apenas relançar
            # para aparecer no console (debug).
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Erro",
                    description=(
                        "Ocorreu um erro ao executar o comando.\n"
                        f"Detalhes: `{error}`"
                    ),
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            raise error

    # ==========================================================
    #                  FUNÇÃO DE CHECAR PERMISSÃO
    # ==========================================================
    async def check_permissions(self, interaction: discord.Interaction, permission: str) -> bool:
        """
        Checa se o autor do comando possui a permissão necessária.
        Exemplo de permissão: 'ban_members', 'kick_members', 'manage_messages', etc.
        Retorna False caso não tenha.
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

    # ==========================================================
    #                      SISTEMA DE LOGS
    # ==========================================================
    async def log_action(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.Member,
        reason: str,
        extra_info: str = ""
    ):
        """
        Registra a ação de moderação em um canal de logs chamado 'logs'.
        Se quiser, pode trocar o nome do canal ou buscar por ID.
        `extra_info` pode incluir mais detalhes sobre a punição.
        """
        log_channel = discord.utils.get(interaction.guild.channels, name="logs")
        if log_channel:
            embed = discord.Embed(
                title=f"📜 Ação de Moderação: {action}",
                description=(
                    f"👤 **Usuário**: {user.mention}\n"
                    f"❓ **Motivo**: {reason}\n"
                    f"👮 **Moderador**: {interaction.user.mention}\n"
                    f"{extra_info}\n"
                    f"📅 **Data**: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                ),
                color=discord.Color.blue()
            )
            await log_channel.send(embed=embed)

    async def send_dm_if_possible(self, user: discord.User, message: str):
        """
        Tenta enviar DM ao usuário. Se não for possível (por privacidade), ignora.
        """
        try:
            await user.send(message)
        except discord.Forbidden:
            # Usuário bloqueou DMs ou algo similar
            pass

    # ==========================================================
    #                   COMANDO TEMPBAN
    # ==========================================================
    @app_commands.command(name="tempban", description="⏳ Bane temporariamente um usuário (em minutos).")
    @app_commands.describe(
        user="Usuário que será banido",
        duration="Duração em minutos",
        reason="Motivo do ban (opcional)",
        dm_user="Enviar DM ao usuário banido? (padrão = False)"
    )
    async def tempban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: int,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        """
        Bane o usuário por X minutos.
        """
        if not await self.check_permissions(interaction, "ban_members"):
            return

        unban_time = datetime.utcnow() + timedelta(minutes=duration)
        self.banned_users.setdefault(interaction.guild.id, {})[user.id] = unban_time

        await interaction.guild.ban(user, reason=reason)

        # Enviar DM se solicitado
        if dm_user:
            await self.send_dm_if_possible(
                user,
                f"Você foi banido temporariamente de **{interaction.guild.name}** por **{duration}** minutos.\n"
                f"**Motivo**: {reason}"
            )

        await self.log_action(interaction, "Ban Temporário", user, reason, extra_info=f"⏰ Duração: {duration}min")

        embed = discord.Embed(
            title="⏳ Ban Temporário",
            description=(
                f"**{user.mention} foi banido por {duration} minutos.**\n"
                f"**Motivo**: {reason}"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                        COMANDO BAN
    # ==========================================================
    @app_commands.command(name="ban", description="🚫 Bane permanentemente um usuário.")
    @app_commands.describe(dm_user="Enviar DM ao usuário banido? (padrão = False)")
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        if not await self.check_permissions(interaction, "ban_members"):
            return

        await interaction.guild.ban(user, reason=reason)

        if dm_user:
            await self.send_dm_if_possible(
                user,
                f"Você foi banido permanentemente de **{interaction.guild.name}**.\n"
                f"**Motivo**: {reason}"
            )

        await self.log_action(interaction, "Ban Permanente", user, reason)

        embed = discord.Embed(
            title="🚫 Ban Permanente",
            description=(
                f"**{user.mention} foi banido permanentemente.**\n"
                f"**Motivo**: {reason}"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                       COMANDO KICK
    # ==========================================================
    @app_commands.command(name="kick", description="👟 Expulsa um usuário do servidor.")
    @app_commands.describe(dm_user="Enviar DM ao usuário expulso? (padrão = False)")
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        if not await self.check_permissions(interaction, "kick_members"):
            return

        await user.kick(reason=reason)

        if dm_user:
            await self.send_dm_if_possible(
                user,
                f"Você foi expulso de **{interaction.guild.name}**.\nMotivo: {reason}"
            )

        await self.log_action(interaction, "Kick", user, reason)

        embed = discord.Embed(
            title="👟 Kick",
            description=(
                f"**{user.mention} foi expulso do servidor.**\n"
                f"**Motivo**: {reason}"
            ),
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                       COMANDO MUTE
    # ==========================================================
    @app_commands.command(name="mute", description="🔇 Silencia um usuário por X minutos (0 = permanente).")
    @app_commands.describe(
        user="Usuário a ser mutado",
        duration="Duração em minutos (0 = permanente)",
        reason="Motivo do mute (opcional)",
        dm_user="Enviar DM ao usuário mutado? (padrão = False)"
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: int = 0,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        """
        Se 'duration' for 0, muta permanentemente até que seja desmutado.
        É necessário ter (ou criar) um papel chamado 'Mutado'.
        """
        if not await self.check_permissions(interaction, "manage_roles"):
            return

        muted_role = discord.utils.get(interaction.guild.roles, name="Mutado")
        if not muted_role:
            # Tenta criar a role
            try:
                muted_role = await interaction.guild.create_role(
                    name="Mutado",
                    reason="Criando papel para Mute."
                )
                for channel in interaction.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Não foi possível criar/adicionar o papel 'Mutado'. Erro: {e}",
                    ephemeral=True
                )
                return

        await user.add_roles(muted_role, reason=reason)

        if dm_user:
            await self.send_dm_if_possible(
                user,
                f"Você foi mutado no servidor **{interaction.guild.name}**.\n"
                f"**Motivo**: {reason}\n"
                f"{'Duração: ' + str(duration) + ' minutos' if duration > 0 else 'Duração indeterminada'}"
            )

        await self.log_action(
            interaction,
            "Mute",
            user,
            reason,
            extra_info=(
                f"Tempo: {duration} minutos" if duration > 0 else "Tempo: Indeterminado"
            )
        )

        if duration > 0:
            embed = discord.Embed(
                title="🔇 Mute Temporário",
                description=(
                    f"**{user.mention} foi silenciado por {duration} minutos.**\n"
                    f"**Motivo**: {reason}"
                ),
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            await self.unmute_after_delay(interaction.guild, user, duration, reason)
        else:
            embed = discord.Embed(
                title="🔇 Mute Permanente",
                description=(
                    f"**{user.mention} foi silenciado por tempo indeterminado.**\n"
                    f"**Motivo**: {reason}"
                ),
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)

    async def unmute_after_delay(
        self,
        guild: discord.Guild,
        user: discord.Member,
        duration: int,
        reason: str
    ):
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=duration))
        muted_role = discord.utils.get(guild.roles, name="Mutado")
        if muted_role and muted_role in user.roles:
            await user.remove_roles(muted_role, reason="Mute expirado")

            channel = discord.utils.get(guild.text_channels, name="logs")
            if channel:
                embed = discord.Embed(
                    title="🔊 Desmute automático",
                    description=(
                        f"**{user.mention} foi desmutado** após {duration} minutos.\n"
                        f"**Motivo original**: {reason}"
                    ),
                    color=discord.Color.green()
                )
                await channel.send(embed=embed)

    # ==========================================================
    #                       COMANDO UNMUTE
    # ==========================================================
    @app_commands.command(name="unmute", description="🔊 Remove o mute de um usuário.")
    @app_commands.describe(dm_user="Enviar DM ao usuário que foi desmutado? (padrão = False)")
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        if not await self.check_permissions(interaction, "manage_roles"):
            return

        muted_role = discord.utils.get(interaction.guild.roles, name="Mutado")
        if muted_role and muted_role in user.roles:
            await user.remove_roles(muted_role, reason=reason)

            if dm_user:
                await self.send_dm_if_possible(
                    user,
                    f"Você foi desmutado no servidor **{interaction.guild.name}**.\n"
                    f"**Motivo**: {reason}"
                )

            await self.log_action(interaction, "Unmute", user, reason)

            embed = discord.Embed(
                title="🔊 Unmute",
                description=(
                    f"**{user.mention} foi desmutado.**\n"
                    f"**Motivo**: {reason}"
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"**{user.mention} não está mutado.**",
                ephemeral=True
            )

    # ==========================================================
    #                      COMANDO WARN
    # ==========================================================
    @app_commands.command(name="warn", description="⚠️ Envia um aviso a um usuário.")
    @app_commands.describe(dm_user="Enviar DM ao usuário avisado? (padrão = False)")
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Não especificado",
        dm_user: bool = False
    ):
        """
        Envia um aviso ao usuário.
        Se atingir certos limites de warns, executa punições automáticas (exemplo).
        """
        if not await self.check_permissions(interaction, "manage_messages"):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        self.warns.setdefault(user.id, 0)
        self.warns[user.id] += 1
        current_warns = self.warns[user.id]

        if dm_user:
            await self.send_dm_if_possible(
                user,
                f"Você recebeu um **warn** no servidor **{interaction.guild.name}**.\nMotivo: {reason}"
            )

        # Ações automáticas dependendo da contagem de warns
        # (Customize como quiser: mute, kick, ban, etc.)
        if current_warns == 3:
            await self.mute(interaction, user, 10, "3 avisos acumulados", dm_user=False)
        elif current_warns == 5:
            await self.kick(interaction, user, "5 avisos acumulados", dm_user=False)
        elif current_warns == 7:
            await self.ban(interaction, user, "7 avisos acumulados - ban permanente", dm_user=False)

        await self.log_action(interaction, "Aviso (Warn)", user, reason)

        embed = discord.Embed(
            title="⚠️ Usuário Avisado",
            description=(
                f"**{user.mention} recebeu um aviso!** (Total de warns: **{current_warns}**)\n"
                f"**Motivo**: {reason}"
            ),
            color=discord.Color.orange()
        )
        # Envia no canal
        await interaction.channel.send(embed=embed)
        # Mensagem ephemeral confirmando ao admin
        await interaction.followup.send("✅ O usuário foi avisado.", ephemeral=True)

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

    # ==========================================================
    #                    COMANDO SLOWMODE
    # ==========================================================
    @app_commands.command(name="slowmode", description="Define o modo lento (slowmode) em segundos.")
    async def slowmode(self, interaction: discord.Interaction, segundos: int):
        if not await self.check_permissions(interaction, "manage_channels"):
            return

        await interaction.channel.edit(slowmode_delay=segundos)
        embed = discord.Embed(
            title="⌛ Slowmode",
            description=f"Modo lento ajustado para `{segundos}` segundos neste canal.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                  COMANDOS LOCK/UNLOCK
    # ==========================================================
    @app_commands.command(name="lockchannel", description="🔒 Tranca o canal (ninguém pode enviar mensagens).")
    async def lock_channel(self, interaction: discord.Interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"):
            return

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        await self.log_action(interaction, "LockChannel", interaction.user, reason)

        embed = discord.Embed(
            title="🔒 Canal Trancado",
            description=f"{interaction.channel.mention} foi **trancado**.\nMotivo: {reason}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlockchannel", description="🔓 Destranca o canal (todos podem enviar mensagens).")
    async def unlock_channel(self, interaction: discord.Interaction, reason: str = "Não especificado"):
        if not await self.check_permissions(interaction, "manage_channels"):
            return

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = True
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        await self.log_action(interaction, "UnlockChannel", interaction.user, reason)

        embed = discord.Embed(
            title="🔓 Canal Destrancado",
            description=f"{interaction.channel.mention} foi **destrancado**.\nMotivo: {reason}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                    COMANDO CLEAR
    # ==========================================================
    @app_commands.command(name="clear", description="🧹 Limpa um número de mensagens do canal.")
    async def clear_messages(self, interaction: discord.Interaction, quantidade: int):
        if not await self.check_permissions(interaction, "manage_messages"):
            return

        await interaction.channel.purge(limit=quantidade+1)  # +1 para remover também o comando do usuário
        embed = discord.Embed(
            title="🧹 Limpeza de Mensagens",
            description=f"Foram deletadas **{quantidade}** mensagens neste canal.",
            color=discord.Color.blurple()
        )
        # Enviar uma mensagem com ephemeral = False (ou True, se preferir)
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    #                    ANTI-SWEAR (BÁSICO)
    # ==========================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.anti_swear_active:
            if message.author.bot or not message.guild:
                return

            msg_lower = message.content.lower()
            for word in self.blocked_words:
                if word in msg_lower:
                    # Deleta a mensagem
                    try:
                        await message.delete()
                        # Logar no canal #logs (opcional)
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
                        break

    @app_commands.command(name="toggleswear", description="🛡️ Liga/Desliga a filtragem de palavrões.")
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

    # ==========================================================
    #                   UNLOAD / FINALIZAÇÃO
    # ==========================================================
    async def cog_unload(self):
        self.tempban_task.cancel()

# Função obrigatória para carregar o cog
async def setup(bot):
    await bot.add_cog(AdminCog(bot))
