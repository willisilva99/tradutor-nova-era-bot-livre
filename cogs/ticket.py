import discord
import random
import string
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

# Ajuste este import conforme o local do seu db.py
from db import SessionLocal, get_or_create_guild_ticket_config, TicketMessage

def gerar_codigo_ticket(tamanho=6):
    """Gera um código aleatório (ex: 'AB12XY') para identificar o ticket."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(tamanho))


# =============================================================================
# 1) GRUPO DE CONFIGURAÇÃO: /ticketconfig
# =============================================================================

class TicketConfigGroup(commands.GroupCog, name="ticketconfig"):
    """
    Grupo de comandos para configurar tickets, usando subcomandos:
      /ticketconfig show
      /ticketconfig staffrole
      /ticketconfig logs
      /ticketconfig avaliation
      /ticketconfig category
    """

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="show", description="Mostra a configuração atual de tickets.")
    @commands.has_permissions(administrator=True)
    async def show(self, interaction: discord.Interaction):
        """Exibe cargo staff, canal de logs, canal avaliação e categoria atuais."""
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cargo = cfg.cargo_staff_id or "Não definido"
            logs = cfg.channel_logs_id or "Não definido"
            avaliation = cfg.channel_avaliation_id or "Não definido"
            category = cfg.category_ticket_id or "Não definido"

            embed = discord.Embed(
                title="Configuração de Tickets",
                description=(
                    f"**Cargo Staff:** `{cargo}`\n"
                    f"**Canal de Logs:** `{logs}`\n"
                    f"**Canal de Avaliação:** `{avaliation}`\n"
                    f"**Categoria:** `{category}`"
                ),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="staffrole", description="Define o cargo staff que controlará os tickets.")
    @commands.has_permissions(administrator=True)
    async def set_staffrole(self, interaction: discord.Interaction, role: discord.Role):
        """
        Exemplo de uso: /ticketconfig staffrole @Staff
        """
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.cargo_staff_id = str(role.id)
            session.commit()
            await interaction.response.send_message(
                f"Cargo staff definido para {role.mention}.",
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(name="logs", description="Define o canal de logs para tickets.")
    @commands.has_permissions(administrator=True)
    async def set_logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Exemplo: /ticketconfig logs #canal-de-logs
        """
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.channel_logs_id = str(channel.id)
            session.commit()
            await interaction.response.send_message(
                f"Canal de logs definido para {channel.mention}.",
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(name="avaliation", description="Define o canal de avaliação dos tickets (feedback).")
    @commands.has_permissions(administrator=True)
    async def set_avaliation(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Exemplo: /ticketconfig avaliation #canal-avaliacao
        """
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.channel_avaliation_id = str(channel.id)
            session.commit()
            await interaction.response.send_message(
                f"Canal de avaliação definido para {channel.mention}.",
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(name="category", description="Define a categoria onde os tickets serão criados.")
    @commands.has_permissions(administrator=True)
    async def set_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        """
        Exemplo: /ticketconfig category #categoria-dos-tickets
        """
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.category_ticket_id = str(category.id)
            session.commit()
            await interaction.response.send_message(
                f"Categoria de tickets definida para {category.name}.",
                ephemeral=True
            )
        finally:
            session.close()


# =============================================================================
# 2) COG PRINCIPAL DO SISTEMA DE TICKETS AVANÇADOS
# =============================================================================

class AdvancedTicketCog(commands.Cog):
    """Cog avançado: /ticketpanel, /reopenticket, auto-fechamento, logs, avaliação etc."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Inicia o loop para fechar tickets inativos
        self.autoclose_loop.start()

    def cog_unload(self):
        self.autoclose_loop.cancel()

    # ~~~~~~~~~~~~~~~~~~~~~ MANEJO DE ERROS ~~~~~~~~~~~~~~~~~~~~~
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """Captura erros de slash commands para debug e feedback."""
        print(f"[APP_COMMAND_ERROR] -> Usuário: {interaction.user}, Erro: {error}")
        # Falta de perm (ex. @commands.has_permissions)
        if isinstance(error, discord.app_commands.CheckFailure):
            try:
                await interaction.response.send_message(
                    "Você não tem permissão para usar este comando!",
                    ephemeral=True
                )
            except:
                pass
            return

        # Qualquer outro erro
        try:
            await interaction.response.send_message(
                f"Ocorreu um erro ao executar este comando: {error}",
                ephemeral=True
            )
        except:
            pass

    # ~~~~~~~~~~~~~~~~~~~~~ COMANDOS ~~~~~~~~~~~~~~~~~~~~~
    @app_commands.command(name="ticketpanel", description="Cria um painel para abertura de tickets.")
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        """Posta um embed + botão 'Abrir Ticket'."""
        embed = discord.Embed(
            title="Painel de Tickets",
            description="Clique no botão abaixo para abrir um ticket!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=TicketPanelView(self.bot))

    @app_commands.command(name="reopenticket", description="Reabre um ticket fechado (renomeia canal).")
    @commands.has_permissions(manage_guild=True)
    async def reopenticket(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        /reopenticket #closed-fulano => renomeia p/ ticket-fulano e restaura permissão do autor
        se constar no topic.
        """
        if not channel.name.startswith("closed-"):
            await interaction.response.send_message("Este canal não está marcado como 'closed-'.", ephemeral=True)
            return

        old_name = channel.name
        new_name = old_name.replace("closed-", "ticket-", 1)
        try:
            await channel.edit(name=new_name)
            # Tenta extrair ID do autor no .topic
            topic = channel.topic or ""
            import re
            match = re.search(r"<@!?(\d+)>", topic)
            if match:
                autor_id = int(match.group(1))
                autor = interaction.guild.get_member(autor_id)
                if autor:
                    overwrites = channel.overwrites
                    overwrites[autor] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    await channel.edit(overwrites=overwrites)

            await interaction.response.send_message(f"Ticket reaberto: {channel.mention}")
        except Exception as e:
            await interaction.response.send_message(f"Falha ao reabrir: {e}", ephemeral=True)

    # ~~~~~~~~~~~~~~~~~~~~~ LOOP PARA AUTO-FECHAR TICKETS ~~~~~~~~~~~~~~~~~~~~~
    @tasks.loop(minutes=10)
    async def autoclose_loop(self):
        """
        A cada 10min, busca canais 'ticket-' sem msg há +60min => renomeia p/ closed-...
        """
        now = datetime.utcnow()
        inatividade_max = timedelta(minutes=60)

        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith("ticket-"):
                    try:
                        history = [m async for m in channel.history(limit=1)]
                        last_msg_time = history[0].created_at if history else channel.created_at
                        if (now - last_msg_time) > inatividade_max:
                            await channel.send("Fechando ticket por inatividade...")
                            new_name = channel.name.replace("ticket-", "closed-")
                            await channel.edit(name=new_name)
                    except Exception as e:
                        print(f"[autoclose_loop] Erro ao fechar {channel.name} inativo: {e}")

    # ~~~~~~~~~~~~~~~~~~~~~ EVENTO on_message P/ LOG DE MENSAGENS ~~~~~~~~~~~~~~~~~~~~~
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return  # ignora DMs
        if message.channel.name.startswith(("ticket-", "closed-")):
            session = SessionLocal()
            try:
                topic = message.channel.topic or ""
                code = "DESCONHECIDO"
                if "Código:" in topic:
                    after = topic.split("Código:")[1].strip()
                    code = after.split()[0].replace("`", "").strip()

                # Salva no BD
                ticket_log = TicketMessage(
                    guild_id=str(message.guild.id),
                    channel_id=str(message.channel.id),
                    ticket_code=code,
                    author_id=str(message.author.id),
                    content=message.content
                )
                session.add(ticket_log)
                session.commit()
            finally:
                session.close()


# =============================================================================
# 3) PARTES DO SISTEMA DE TICKETS: Views / Modals
# =============================================================================

class TicketPanelView(discord.ui.View):
    """View com botão para abrir ticket (usado em /ticketpanel)."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="abrir_ticket")
    async def abrir_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Exibe modal p/ coletar o motivo do ticket."""
        modal = AbrirTicketModal(self.bot)
        await interaction.response.send_modal(modal)


class AbrirTicketModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot):
        super().__init__(title="Abrir Ticket")
        self.bot = bot
        self.motivo = discord.ui.TextInput(
            label="Descreva o motivo do ticket",
            style=discord.TextStyle.long,
            placeholder="Ex: Preciso de ajuda com tal coisa...",
            required=True
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        # Carregar config e criar canal
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            guild = interaction.guild
            staff_role = guild.get_role(int(cfg.cargo_staff_id)) if cfg.cargo_staff_id else None
            logs_ch = guild.get_channel(int(cfg.channel_logs_id)) if cfg.channel_logs_id else None
            avaliations_ch = guild.get_channel(int(cfg.channel_avaliation_id)) if cfg.channel_avaliation_id else None
            category_ch = guild.get_channel(int(cfg.category_ticket_id)) if cfg.category_ticket_id else None

            code = gerar_codigo_ticket()
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            channel_name = f"ticket-{interaction.user.name}"
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category_ch,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user.mention} | Código: {code}"
            )

            embed = discord.Embed(
                title="Ticket Aberto",
                description=(
                    f"**Usuário:** {interaction.user.mention}\n"
                    f"**Motivo:** {self.motivo.value}\n"
                    f"**Código:** `{code}`\n"
                    "Ninguém assumiu ainda."
                ),
                color=discord.Color.blue()
            )
            view = TicketChannelView(
                autor_ticket=interaction.user,
                staff_role=staff_role,
                code=code,
                logs_channel=logs_ch,
                avaliations_channel=avaliations_ch
            )
            await ticket_channel.send(
                content=f"{interaction.user.mention} {staff_role.mention if staff_role else ''}",
                embed=embed,
                view=view
            )

            # Log no canal
            if logs_ch:
                log_embed = discord.Embed(
                    title="Novo Ticket Aberto",
                    description=(
                        f"**Usuário:** {interaction.user.mention}\n"
                        f"**Canal:** {ticket_channel.mention}\n"
                        f"**Motivo:** {self.motivo.value}\n"
                        f"**Código:** {code}"
                    ),
                    color=discord.Color.green()
                )
                await logs_ch.send(embed=log_embed)

            await interaction.response.send_message(
                f"Ticket criado com sucesso em {ticket_channel.mention}!",
                ephemeral=True
            )
        finally:
            session.close()


class TicketChannelView(discord.ui.View):
    """
    Botões de controle dentro do canal do ticket:
    - Painel Staff (StaffSelectView)
    - Painel Membro (MemberSelectView)
    - Assumir Ticket
    - Sair do Ticket
    - Finalizar Ticket
    """
    def __init__(self, autor_ticket: discord.User, staff_role: discord.Role,
                 code: str, logs_channel: discord.TextChannel, avaliations_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor_ticket = autor_ticket
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel
        self.avaliations_channel = avaliations_channel

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, custom_id="painel_staff")
    async def painel_staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Somente staff pode usar este painel.", ephemeral=True)
            return
        view = StaffSelectView(
            autor_ticket=self.autor_ticket,
            staff_role=self.staff_role,
            code=self.code,
            logs_channel=self.logs_channel
        )
        await interaction.response.send_message("Escolha uma ação de staff:", view=view, ephemeral=True)

    @discord.ui.button(label="Painel Membro", style=discord.ButtonStyle.secondary, custom_id="painel_membro")
    async def painel_membro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_ticket.id:
            await interaction.response.send_message("Somente o autor do ticket pode usar este painel.", ephemeral=True)
            return
        view = MemberSelectView(
            autor_ticket=self.autor_ticket,
            staff_role=self.staff_role,
            code=self.code,
            logs_channel=self.logs_channel
        )
        await interaction.response.send_message("Escolha uma ação de membro:", view=view, ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.success, custom_id="ticket_assumir")
    async def ticket_assumir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Apenas staff pode assumir este ticket!", ephemeral=True)
            return
        # Edita a embed para indicar quem assumiu
        msg = interaction.message
        if msg and msg.embeds:
            embed_atual = msg.embeds[0]
            desc = embed_atual.description
            if "Ninguém assumiu ainda." in desc:
                desc = desc.replace("Ninguém assumiu ainda.", f"Assumido por {interaction.user.mention}.")
            else:
                desc += f"\nAssumido por {interaction.user.mention}."
            new_embed = discord.Embed(title=embed_atual.title, description=desc, color=discord.Color.blue())
            await msg.edit(embed=new_embed, view=self)

        await interaction.response.send_message("Você assumiu o ticket!", ephemeral=True)

        # Log
        if self.logs_channel:
            await self.logs_channel.send(embed=discord.Embed(
                title="Ticket Assumido",
                description=(
                    f"**Canal:** {interaction.channel.mention}\n"
                    f"**Staff:** {interaction.user.mention}\n"
                    f"**Código:** {self.code}"
                ),
                color=discord.Color.orange()
            ))

    @discord.ui.button(label="Sair do Ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_sair")
    async def ticket_sair_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_ticket.id:
            await interaction.response.send_message("Somente o autor pode sair.", ephemeral=True)
            return
        overwrites = interaction.channel.overwrites
        if interaction.user in overwrites:
            overwrites[interaction.user].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)
        await interaction.response.send_message("Você saiu do ticket.", ephemeral=True)

    @discord.ui.button(label="Finalizar Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_fechar")
    async def ticket_fechar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Apenas staff pode fechar este ticket!", ephemeral=True)
            return
        await interaction.response.defer()

        old_name = interaction.channel.name
        new_name = old_name.replace("ticket-", "closed-")
        await interaction.channel.edit(name=new_name)

        overwrites = interaction.channel.overwrites
        if self.autor_ticket in overwrites:
            overwrites[self.autor_ticket].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)

        if self.logs_channel:
            await self.logs_channel.send(embed=discord.Embed(
                title="Ticket Fechado",
                description=(
                    f"**Canal:** {interaction.channel.mention}\n"
                    f"**Fechado por:** {interaction.user.mention}\n"
                    f"**Código:** {self.code}"
                ),
                color=discord.Color.red()
            ))

        await interaction.followup.send(
            "Ticket fechado! (Canal renomeado para 'closed-').",
            ephemeral=True
        )

        # Envia DM ao autor para avaliação
        try:
            await self.enviar_avaliacao_dm()
        except:
            pass

    async def enviar_avaliacao_dm(self):
        if not self.avaliations_channel:
            return
        user = self.autor_ticket
        try:
            dm = await user.create_dm()
            embed = discord.Embed(
                title="Avalie seu Ticket",
                description="Escolha uma **nota de 1 a 5** e deixe um comentário do atendimento.",
                color=discord.Color.green()
            )
            await dm.send(embed=embed)
            view = discord.ui.View()
            button = discord.ui.Button(label="Avaliar", style=discord.ButtonStyle.primary)

            async def callback(i: discord.Interaction):
                if i.user.id == user.id:
                    modal = AvaliacaoModal(self.avaliations_channel, self.code)
                    await i.response.send_modal(modal)
                else:
                    await i.response.send_message("Você não pode abrir o modal de outra pessoa!", ephemeral=True)

            button.callback = callback
            view.add_item(button)
            await dm.send(view=view)
        except:
            pass


# ===================== STAFF SELECT & MEMBER SELECT ===================== #

class StaffSelectView(discord.ui.View):
    """Select menu com ações: chamar autor, add/remove user, criar/deletar call, transferir ticket."""
    def __init__(self, autor_ticket: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor_ticket = autor_ticket
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel

        self.select = discord.ui.Select(
            placeholder="Selecione uma ação de Staff",
            options=[
                discord.SelectOption(label="Chamar Autor", value="chamar_autor"),
                discord.SelectOption(label="Adicionar Usuário", value="add_user"),
                discord.SelectOption(label="Remover Usuário", value="remove_user"),
                discord.SelectOption(label="Criar Call de Voz", value="create_call"),
                discord.SelectOption(label="Deletar Call de Voz", value="delete_call"),
                discord.SelectOption(label="Transferir Ticket", value="transfer_ticket"),
            ],
            custom_id="staff_select"
        )
        self.add_item(self.select)

    @discord.ui.select(custom_id="staff_select")
    async def staff_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        op = select.values[0]

        # Verifica se user é staff
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Apenas staff pode usar este menu!", ephemeral=True)
            return

        if op == "chamar_autor":
            try:
                await self.autor_ticket.send(
                    f"O staff {interaction.user.mention} está chamando você no ticket {interaction.channel.mention}!"
                )
                await interaction.response.send_message("Autor notificado por DM!", ephemeral=True)
            except:
                await interaction.response.send_message("Falha ao enviar DM ao autor.", ephemeral=True)

        elif op == "add_user":
            await interaction.response.send_message("Digite o ID ou mencione o usuário a adicionar:", ephemeral=True)
            await self._aguardar_usuario(interaction, adicionar=True)

        elif op == "remove_user":
            await interaction.response.send_message("Digite o ID ou mencione o usuário a remover:", ephemeral=True)
            await self._aguardar_usuario(interaction, adicionar=False)

        elif op == "create_call":
            await self._create_call(interaction)

        elif op == "delete_call":
            await self._delete_call(interaction)

        elif op == "transfer_ticket":
            await interaction.response.send_message("Digite o ID do novo cargo staff:", ephemeral=True)
            await self._transferir_ticket(interaction)

    async def _aguardar_usuario(self, interaction: discord.Interaction, adicionar: bool):
        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel == interaction.channel

        try:
            msg = await self.select.view.bot.wait_for("message", check=check, timeout=60)
        except:
            await interaction.followup.send("Tempo esgotado!", ephemeral=True)
            return

        user = None
        if msg.mentions:
            user = msg.mentions[0]
        else:
            try:
                user_id = int(msg.content)
                user = interaction.guild.get_member(user_id)
            except:
                pass
        if not user:
            await interaction.followup.send("Usuário não encontrado!", ephemeral=True)
            return

        overwrites = interaction.channel.overwrites
        if adicionar:
            overwrites[user] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            await interaction.channel.edit(overwrites=overwrites)
            await interaction.followup.send(f"Usuário {user.mention} agora tem acesso!", ephemeral=True)
        else:
            if user not in overwrites:
                await interaction.followup.send("Este usuário não tinha acesso.", ephemeral=True)
                return
            overwrites[user].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)
            await interaction.followup.send(f"Usuário {user.mention} removido do ticket.", ephemeral=True)

    async def _create_call(self, interaction: discord.Interaction):
        guild = interaction.guild
        call_name = f"call-{interaction.channel.name}"
        existing = discord.utils.get(guild.voice_channels, name=call_name)
        if existing:
            await interaction.followup.send(f"Já existe a call {existing.mention}!", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        overwrites[self.autor_ticket] = discord.PermissionOverwrite(view_channel=True, speak=True)
        if self.staff_role:
            overwrites[self.staff_role] = discord.PermissionOverwrite(view_channel=True, speak=True)

        call_channel = await guild.create_voice_channel(
            name=call_name,
            overwrites=overwrites,
            category=interaction.channel.category
        )
        await interaction.followup.send(f"Call de voz criada: {call_channel.mention}", ephemeral=True)

    async def _delete_call(self, interaction: discord.Interaction):
        guild = interaction.guild
        call_name = f"call-{interaction.channel.name}"
        existing = discord.utils.get(guild.voice_channels, name=call_name)
        if not existing:
            await interaction.followup.send("Não existe call para deletar!", ephemeral=True)
            return
        await existing.delete(reason="Removendo call do ticket")
        await interaction.followup.send("Call de voz deletada!", ephemeral=True)

    async def _transferir_ticket(self, interaction: discord.Interaction):
        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel == interaction.channel

        try:
            msg = await self.select.view.bot.wait_for("message", check=check, timeout=60)
        except:
            await interaction.followup.send("Tempo esgotado!", ephemeral=True)
            return

        try:
            cargo_id = int(msg.content)
            new_role = interaction.guild.get_role(cargo_id)
            if not new_role:
                await interaction.followup.send("Cargo não encontrado!", ephemeral=True)
                return

            overwrites = interaction.channel.overwrites
            if self.staff_role in overwrites:
                overwrites[self.staff_role].view_channel = False
            overwrites[new_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            await interaction.channel.edit(overwrites=overwrites)

            if self.logs_channel:
                await self.logs_channel.send(
                    f"Ticket {interaction.channel.mention} transferido de {self.staff_role.mention} para {new_role.mention}."
                )
            await interaction.followup.send(f"Ticket transferido para {new_role.mention}!", ephemeral=True)
        except:
            await interaction.followup.send("ID de cargo inválido!", ephemeral=True)


class MemberSelectView(discord.ui.View):
    """Select menu com ações para o autor do ticket: chamar staff, criar/deletar call."""
    def __init__(self, autor_ticket: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor_ticket = autor_ticket
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel

        self.select = discord.ui.Select(
            placeholder="Selecione uma ação de Membro",
            options=[
                discord.SelectOption(label="Chamar Staff", value="chamar_staff"),
                discord.SelectOption(label="Criar Call de Voz", value="create_call"),
                discord.SelectOption(label="Deletar Call de Voz", value="delete_call"),
            ],
            custom_id="membro_select"
        )
        self.add_item(self.select)

    @discord.ui.select(custom_id="membro_select")
    async def membro_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        op = select.values[0]
        if interaction.user.id != self.autor_ticket.id:
            await interaction.response.send_message("Somente o autor do ticket pode usar isto!", ephemeral=True)
            return

        if op == "chamar_staff":
            if self.logs_channel:
                await self.logs_channel.send(
                    f"{interaction.user.mention} chamou o staff no ticket {interaction.channel.mention}"
                )
            await interaction.response.send_message("Staff notificado!", ephemeral=True)

        elif op == "create_call":
            await self._create_call(interaction)

        elif op == "delete_call":
            await self._delete_call(interaction)

    async def _create_call(self, interaction: discord.Interaction):
        guild = interaction.guild
        call_name = f"call-{interaction.channel.name}"
        existing = discord.utils.get(guild.voice_channels, name=call_name)
        if existing:
            await interaction.followup.send(f"Já existe a call {existing.mention}!", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        overwrites[self.autor_ticket] = discord.PermissionOverwrite(view_channel=True, speak=True)
        if self.staff_role:
            overwrites[self.staff_role] = discord.PermissionOverwrite(view_channel=True, speak=True)

        call_channel = await guild.create_voice_channel(
            name=call_name,
            overwrites=overwrites,
            category=interaction.channel.category
        )
        await interaction.followup.send(f"Call de voz criada: {call_channel.mention}", ephemeral=True)

    async def _delete_call(self, interaction: discord.Interaction):
        guild = interaction.guild
        call_name = f"call-{interaction.channel.name}"
        existing = discord.utils.get(guild.voice_channels, name=call_name)
        if not existing:
            await interaction.followup.send("Não existe call para deletar!", ephemeral=True)
            return
        await existing.delete(reason="Deletando call do ticket")
        await interaction.followup.send("Call de voz deletada!", ephemeral=True)


class AvaliacaoModal(discord.ui.Modal):
    """Modal para avaliar o atendimento (1 a 5 + comentário)."""
    def __init__(self, avaliations_channel: discord.TextChannel, code: str):
        super().__init__(title="Avalie o Atendimento")
        self.avaliations_channel = avaliations_channel
        self.code = code

        self.nota = discord.ui.TextInput(
            label="Nota (1 a 5)",
            placeholder="Ex: 5",
            max_length=1
        )
        self.comentario = discord.ui.TextInput(
            label="Comentário (opcional)",
            style=discord.TextStyle.long,
            placeholder="O que achou do atendimento?"
        )
        self.add_item(self.nota)
        self.add_item(self.comentario)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.nota.value)
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            await interaction.response.send_message("Nota inválida! Use um número de 1 a 5.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Nova Avaliação de Ticket",
            description=(
                f"**Usuário:** {interaction.user.mention}\n"
                f"**Código:** {self.code}\n"
                f"**Nota:** {rating}/5\n"
                f"**Comentário:** {self.comentario.value}"
            ),
            color=discord.Color.yellow()
        )
        if self.avaliations_channel:
            await self.avaliations_channel.send(embed=embed)

        await interaction.response.send_message("Obrigado pela sua avaliação!", ephemeral=True)


# =============================================================================
# 4) SETUP: ADICIONANDO AS DUAS COGS NO MESMO ARQUIVO
# =============================================================================

async def setup(bot: commands.Bot):
    """
    Este setup adiciona as duas cogs:
      - TicketConfigGroup (subcomandos /ticketconfig ...)
      - AdvancedTicketCog (sistema de tickets completo)
    """
    await bot.add_cog(TicketConfigGroup(bot))
    await bot.add_cog(AdvancedTicketCog(bot))
