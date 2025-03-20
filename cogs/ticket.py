import discord
import random
import string
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

from db import (
    SessionLocal,
    get_or_create_guild_ticket_config,
    TicketMessage
)

# ===================== FUNÇÕES AUXILIARES ===================== #

def gerar_codigo_ticket(tamanho=6):
    """Gera código aleatório (ex: AB12XY)."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(tamanho))

# ===================== COG PRINCIPAL ===================== #

class AdvancedTicketCog(commands.Cog):
    """Cog avançado que engloba configuração, criação e gestão de tickets + melhorias."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Loop para fechar tickets inativos
        self.autoclose_loop.start()

    def cog_unload(self):
        self.autoclose_loop.cancel()

    # ---------- 1) PAINEL DE CONFIGURAÇÃO ---------- #
    @app_commands.command(name="ticketconfig", description="Menu de Configuração Avançada do Sistema de Tickets.")
    @commands.has_permissions(administrator=True)
    async def ticketconfig(self, interaction: discord.Interaction):
        """
        Comando principal para configuração via menu:
        - Cargo Staff
        - Canal de Logs
        - Canal de Avaliação
        - Categoria
        """
        # Carrega config do BD (ou cria se não existir)
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
        finally:
            session.close()

        embed = discord.Embed(
            title="Configuração de Tickets",
            description=(
                "Selecione abaixo a opção que deseja configurar:\n\n"
                "**Cargo Staff**: Pode assumir/fechar tickets.\n"
                "**Canal de Logs**: Recebe logs de abertura/fechamento/assunção.\n"
                "**Canal de Avaliação**: Recebe avaliações de 1 a 5 (feedback do atendimento).\n"
                "**Categoria**: Onde criar os canais de ticket.\n"
            ),
            color=discord.Color.blurple()
        )
        view = ConfigTicketView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ---------- 2) COMANDO PARA CRIAR PAINEL DE TICKET ---------- #
    @app_commands.command(name="ticketpanel", description="Cria um painel para abertura de tickets.")
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Painel de Tickets",
            description="Clique no botão abaixo para abrir um ticket!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=TicketPanelView(self.bot))

    # ---------- 3) COMANDO PARA REABRIR UM TICKET FECHADO ---------- #
    @app_commands.command(name="reopenticket", description="Reabre um ticket fechado recentemente (renomeia canal).")
    @commands.has_permissions(manage_guild=True)
    async def reopenticket(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Exemplo de uso: /reopenticket #closed-fulano
        Se o canal estiver 'closed-', renomeia para 'ticket-' e restaura permissões do autor.
        """
        if not channel.name.startswith("closed-"):
            await interaction.response.send_message("Este canal não está marcado como 'closed-'.", ephemeral=True)
            return

        # Tenta restaurar
        old_name = channel.name
        new_name = old_name.replace("closed-", "ticket-", 1)
        try:
            await channel.edit(name=new_name)
            # Restaure as permissões do autor, se precisar.  
            # Se guardamos o autor no topic ou algo assim, extraia e dê permissão a ele.
            topic = channel.topic or ""
            # Exemplo: "Ticket de <@123456> | Código: AB12CD"
            # Extraímos ID do autor. Se não achar, ignore.
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

    # ---------- 4) LOOP PARA FECHAR TICKETS INATIVOS ---------- #
    @tasks.loop(minutes=10)
    async def autoclose_loop(self):
        """
        A cada 10 minutos, procura canais 'ticket-' e verifica a última mensagem.
        Se passaram, por exemplo, 60 minutos sem mensagem, fecha o ticket.
        """
        now = datetime.utcnow()
        # Ajuste o tempo de inatividade que achar melhor
        inatividade_max = timedelta(minutes=60)

        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith("ticket-"):
                    # Pega últimas mensagens
                    try:
                        history = [m async for m in channel.history(limit=1)]
                        if history:
                            last_msg_time = history[0].created_at
                        else:
                            # Se não tem nenhuma mensagem, considere a data de criação do canal
                            last_msg_time = channel.created_at

                        if (now - last_msg_time) > inatividade_max:
                            # Fecha o ticket => renomeia para closed-...
                            await channel.send("Fechando ticket por inatividade...")
                            new_name = channel.name.replace("ticket-", "closed-")
                            await channel.edit(name=new_name)
                            # Remove permissões do autor se quiser. No ex. só rename.
                    except:
                        pass

    # ---------- 5) EVENTO on_message PARA REGISTRAR MENSAGENS NO BD ---------- #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return  # Ignora DMs

        # Verifica se é um canal de ticket ou closed
        if message.channel.name.startswith(("ticket-", "closed-")):
            session = SessionLocal()
            try:
                # Tenta extrair "Código: XXX" do topic do canal
                topic = message.channel.topic or ""
                code = "DESCONHECIDO"
                # Exemplo de topic: "Ticket de @Fulano | Código: AB12CD"
                if "Código:" in topic:
                    after = topic.split("Código:")[1].strip()
                    code = after.split()[0].replace("`", "").strip()

                # Salva no BD
                ticket_log = TicketMessage(
                    guild_id=str(message.guild.id),
                    channel_id=str(message.channel.id),
                    ticket_code=code,
                    author_id=str(message.author.id),
                    content=message.content,
                )
                session.add(ticket_log)
                session.commit()
            finally:
                session.close()

# ------------------------------------------------
#                PAINEL DE CONFIG VIEW
# ------------------------------------------------

class ConfigTicketView(discord.ui.View):
    """Menu para escolher o que configurar no ticket."""
    def __init__(self):
        super().__init__(timeout=None)
        # Adiciona o select menu:
        options = [
            discord.SelectOption(label="Definir Cargo Staff", value="staffrole"),
            discord.SelectOption(label="Definir Canal de Logs", value="logs"),
            discord.SelectOption(label="Definir Canal de Avaliação", value="avaliation"),
            discord.SelectOption(label="Definir Categoria", value="category"),
        ]
        self.select = discord.ui.Select(
            placeholder="Escolha o que configurar...",
            options=options,
            custom_id="config_ticket_select"
        )
        self.add_item(self.select)

    @discord.ui.select(custom_id="config_ticket_select")
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]
        if value == "staffrole":
            # Abre modal para staff role (não existe "Role" input nativo em modals)
            # Precisamos pedir ID ou menção. Faremos com modal:
            modal = ConfigSetStaffRoleModal()
            await interaction.response.send_modal(modal)
        elif value == "logs":
            modal = ConfigSetLogsModal()
            await interaction.response.send_modal(modal)
        elif value == "avaliation":
            modal = ConfigSetAvaliationsModal()
            await interaction.response.send_modal(modal)
        elif value == "category":
            modal = ConfigSetCategoryModal()
            await interaction.response.send_modal(modal)

# ----------- MODAIS DE CONFIGURAÇÃO ----------- #
# Todos iguais: pedem ao usuário um ID e salvam no BD.

class ConfigSetStaffRoleModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Definir Cargo Staff")
        self.role_input = discord.ui.TextInput(
            label="ID do Cargo Staff",
            placeholder="Exemplo: 123456789012345678",
            required=True
        )
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        role_id_str = self.role_input.value.strip()
        try:
            role_id = int(role_id_str)
        except:
            await interaction.response.send_message("ID inválido!", ephemeral=True)
            return
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.cargo_staff_id = str(role_id)
            session.commit()
            await interaction.response.send_message(f"Cargo staff definido para ID `{role_id}`!", ephemeral=True)
        finally:
            session.close()

class ConfigSetLogsModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Definir Canal de Logs")
        self.channel_input = discord.ui.TextInput(
            label="ID do Canal de Logs",
            placeholder="Exemplo: 123456789012345678",
            required=True
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except:
            await interaction.response.send_message("ID inválido!", ephemeral=True)
            return
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.channel_logs_id = str(channel_id)
            session.commit()
            await interaction.response.send_message(f"Canal de logs definido para ID `{channel_id}`!", ephemeral=True)
        finally:
            session.close()

class ConfigSetAvaliationsModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Definir Canal de Avaliação")
        self.channel_input = discord.ui.TextInput(
            label="ID do Canal de Avaliação",
            placeholder="Exemplo: 987654321098765432",
            required=True
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except:
            await interaction.response.send_message("ID inválido!", ephemeral=True)
            return
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.channel_avaliation_id = str(channel_id)
            session.commit()
            await interaction.response.send_message(f"Canal de avaliação definido para `{channel_id}`!", ephemeral=True)
        finally:
            session.close()

class ConfigSetCategoryModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Definir Categoria de Tickets")
        self.cat_input = discord.ui.TextInput(
            label="ID da Categoria",
            placeholder="Exemplo: 987654321012345678",
            required=True
        )
        self.add_item(self.cat_input)

    async def on_submit(self, interaction: discord.Interaction):
        cat_id_str = self.cat_input.value.strip()
        try:
            cat_id = int(cat_id_str)
        except:
            await interaction.response.send_message("ID inválido!", ephemeral=True)
            return
        session = SessionLocal()
        try:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cfg.category_ticket_id = str(cat_id)
            session.commit()
            await interaction.response.send_message(f"Categoria de tickets definida para `{cat_id}`!", ephemeral=True)
        finally:
            session.close()

# ------------------------------------------------
#           CRIAÇÃO DE TICKET - PAINEL
# ------------------------------------------------

class TicketPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="abrir_ticket")
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre um modal perguntando o motivo do ticket."""
        modal = AbrirTicketModal(self.bot)
        await interaction.response.send_modal(modal)

class AbrirTicketModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot):
        super().__init__(title="Abrir Ticket")
        self.bot = bot
        self.motivo = discord.ui.TextInput(
            label="Descreva o motivo do ticket",
            style=discord.TextStyle.long,
            placeholder="Ex: Preciso de ajuda com XYZ",
            required=True
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        # Lê config do DB
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

            # Cria canal com "ticket-{nome}"
            channel_name = f"ticket-{interaction.user.name}"
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category_ch,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user.mention} | Código: {code}"
            )
            # Mensagem inicial
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

            # Log
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
                f"Seu ticket foi criado: {ticket_channel.mention}",
                ephemeral=True
            )
        finally:
            session.close()

# ------------------------------------------------
#     GERENCIAR TICKET DENTRO DO CANAL (VIEW)
# ------------------------------------------------

class TicketChannelView(discord.ui.View):
    """
    Botões + menus para gerenciar o ticket:
    - Painel Staff
    - Painel Membro
    - Assumir Ticket
    - Finalizar (ou Fechar)
    - Sair do Ticket
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
        await interaction.response.send_message("Escolha uma opção de staff:", view=view, ephemeral=True)

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
        await interaction.response.send_message("Escolha uma opção de membro:", view=view, ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.success, custom_id="ticket_assumir")
    async def ticket_assumir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Apenas staff pode assumir este ticket!", ephemeral=True)
            return
        msg = interaction.message
        if msg.embeds:
            embed_atual = msg.embeds[0]
            desc = embed_atual.description
            if "Ninguém assumiu ainda." in desc:
                desc = desc.replace("Ninguém assumiu ainda.", f"Assumido por {interaction.user.mention}.")
            else:
                desc += f"\nAssumido por {interaction.user.mention}."
            new_embed = discord.Embed(title=embed_atual.title, description=desc, color=discord.Color.blue())
            await msg.edit(embed=new_embed, view=self)
        await interaction.response.send_message("Você assumiu este ticket!", ephemeral=True)
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
            await interaction.response.send_message("Somente o autor do ticket pode sair.", ephemeral=True)
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

        # Renomeia para closed- e remove permissões do autor, em vez de apagar canal:
        old_name = interaction.channel.name
        new_name = old_name.replace("ticket-", "closed-")
        await interaction.channel.edit(name=new_name)
        # Remove autor
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

        await interaction.followup.send("Ticket fechado! (Canal renomeado para 'closed-').", ephemeral=True)

        # Envia DM para autor pedindo avaliação
        try:
            await self.enviar_avaliacao_dm()
        except:
            pass

    async def enviar_avaliacao_dm(self):
        user = self.autor_ticket
        if not self.avaliations_channel:
            return  # Se não tem canal de avaliação configurado, ignore

        try:
            dm = await user.create_dm()
            embed = discord.Embed(
                title="Avalie seu Ticket",
                description=(
                    "Obrigado por usar nosso suporte!\n\n"
                    "Por favor, escolha uma **nota de 1 a 5** e deixe um comentário sobre o atendimento."
                ),
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

# ------------------------------------------------
#         SELECT MENUS DE STAFF/MEMBRO
# ------------------------------------------------

class StaffSelectView(discord.ui.View):
    """Select menu para ações de staff no ticket."""
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
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message("Apenas staff pode usar isso!", ephemeral=True)
            return

        if op == "chamar_autor":
            try:
                await self.autor_ticket.send(f"O staff {interaction.user.mention} está chamando você no ticket {interaction.channel.mention}!")
                await interaction.response.send_message("Autor notificado por DM!", ephemeral=True)
            except:
                await interaction.response.send_message("Não foi possível enviar DM ao autor.", ephemeral=True)

        elif op == "add_user":
            await interaction.response.send_message("Digite o ID ou mencione o usuário para adicionar:", ephemeral=True)
            await self._aguardar_usuario(interaction, adicionar=True)

        elif op == "remove_user":
            await interaction.response.send_message("Digite o ID ou mencione o usuário para remover:", ephemeral=True)
            await self._aguardar_usuario(interaction, adicionar=False)

        elif op == "create_call":
            await self._create_call(interaction)

        elif op == "delete_call":
            await self._delete_call(interaction)

        elif op == "transfer_ticket":
            await interaction.response.send_message("Digite o ID do novo cargo staff para transferência:", ephemeral=True)
            await self._transferir_ticket(interaction)

class MemberSelectView(discord.ui.View):
    """Select menu para ações do autor do ticket."""
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
            await interaction.response.send_message("Somente o autor pode usar isso!", ephemeral=True)
            return

        if op == "chamar_staff":
            # Pode notificar canal de logs ou staff
            if self.logs_channel:
                await self.logs_channel.send(f"{interaction.user.mention} chamou o staff no ticket {interaction.channel.mention}.")
            await interaction.response.send_message("Staff notificado!", ephemeral=True)

        elif op == "create_call":
            await self._create_call(interaction)

        elif op == "delete_call":
            await self._delete_call(interaction)


# ------------------------------------------------
#       AÇÕES EM COMUM (STAFF E MEMBRO)
# ------------------------------------------------

async def _create_call(self, interaction: discord.Interaction):
    # Nome da call = call-{canal.text}
    guild = interaction.guild
    call_name = f"call-{interaction.channel.name}"
    existing = discord.utils.get(guild.voice_channels, name=call_name)
    if existing:
        await interaction.followup.send(f"Já existe a call {existing.mention}!", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    # Autor
    overwrites[self.autor_ticket] = discord.PermissionOverwrite(view_channel=True, speak=True)
    # Staff
    if self.staff_role:
        overwrites[self.staff_role] = discord.PermissionOverwrite(view_channel=True, speak=True)

    call_channel = await guild.create_voice_channel(
        name=call_name,
        overwrites=overwrites,
        category=interaction.channel.category,
        reason="Criando call para ticket"
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


# Para simplificar, podemos "monkey patch" no StaffSelectView e MemberSelectView.
# Faremos manualmente:
StaffSelectView._create_call = _create_call
StaffSelectView._delete_call = _delete_call
MemberSelectView._create_call = _create_call
MemberSelectView._delete_call = _delete_call


# ------------------------------------------------
#  ADICIONAR E REMOVER USUÁRIO
# ------------------------------------------------

async def _aguardar_usuario(self, interaction: discord.Interaction, adicionar: bool):
    def check(msg: discord.Message):
        return msg.author.id == interaction.user.id and msg.channel == interaction.channel
    try:
        msg = await self.bot.wait_for("message", check=check, timeout=60)
    except:
        await interaction.followup.send("Tempo esgotado!", ephemeral=True)
        return

    # Tenta parsear
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

    if adicionar:
        overwrites = interaction.channel.overwrites
        overwrites[user] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        await interaction.channel.edit(overwrites=overwrites)
        await interaction.followup.send(f"O usuário {user.mention} agora tem acesso ao ticket.", ephemeral=True)
    else:
        overwrites = interaction.channel.overwrites
        if user not in overwrites:
            await interaction.followup.send("Este usuário não tinha acesso.", ephemeral=True)
            return
        overwrites[user].view_channel = False
        await interaction.channel.edit(overwrites=overwrites)
        await interaction.followup.send(f"O usuário {user.mention} foi removido do ticket.", ephemeral=True)

StaffSelectView._aguardar_usuario = _aguardar_usuario

# ------------------------------------------------
#        TRANSFERIR TICKET PARA OUTRO CARGO
# ------------------------------------------------

async def _transferir_ticket(self, interaction: discord.Interaction):
    def check(msg: discord.Message):
        return msg.author.id == interaction.user.id and msg.channel == interaction.channel
    try:
        msg = await self.bot.wait_for("message", check=check, timeout=60)
    except:
        await interaction.followup.send("Tempo esgotado!", ephemeral=True)
        return
    try:
        cargo_id = int(msg.content)
        new_role = interaction.guild.get_role(cargo_id)
        if not new_role:
            await interaction.followup.send("Cargo não encontrado!", ephemeral=True)
            return
        # Remove permissões do cargo staff antigo e concede ao novo
        overwrites = interaction.channel.overwrites
        if self.staff_role in overwrites:
            overwrites[self.staff_role].view_channel = False
        overwrites[new_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        await interaction.channel.edit(overwrites=overwrites)

        # Log
        if self.logs_channel:
            await self.logs_channel.send(
                f"O ticket {interaction.channel.mention} foi transferido de {self.staff_role.mention if self.staff_role else '???'} para {new_role.mention}."
            )
        await interaction.followup.send(f"Ticket transferido para o cargo {new_role.mention}!", ephemeral=True)
    except:
        await interaction.followup.send("ID de cargo inválido!", ephemeral=True)

StaffSelectView._transferir_ticket = _transferir_ticket

# ------------------------------------------------
#         MODAL DE AVALIAÇÃO FINAL
# ------------------------------------------------

class AvaliacaoModal(discord.ui.Modal):
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

# ------------------------------------------------
#     SETUP COG
# ------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(AdvancedTicketCog(bot))
