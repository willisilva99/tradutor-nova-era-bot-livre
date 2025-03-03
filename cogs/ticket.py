Vamos revisar o código para garantir que a personalização do ticket esteja funcionando corretamente. A seguir está um arquivo Python completo com as correções e melhorias necessárias para garantir que a personalização do embed funcione corretamente.

```python name=ticket_bot.py
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from datetime import datetime
import asyncio
import os

# SQLAlchemy Imports
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSON

#############################################
# 1) CONFIGURAÇÃO DO BANCO E MODELOS
#############################################
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERRO: A variável de ambiente DATABASE_URL não está definida.")

engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TicketUserData(Base):
    __tablename__ = "ticket_user_data"
    user_id = Column(String, primary_key=True, index=True)
    ticket_count = Column(Integer, default=0)
    open_tickets = Column(Integer, default=0)

class TicketGuildSettings(Base):
    __tablename__ = "ticket_guild_settings"
    guild_id = Column(String, primary_key=True, index=True)
    custom_ticket_settings = Column(JSON, nullable=True, default={})
    support_roles = Column(JSON, nullable=True, default=[])
    logs_channel = Column(String, nullable=True)
    evaluation_channel = Column(String, nullable=True)

class BlacklistedUser(Base):
    __tablename__ = "blacklisted_users"
    user_id = Column(String, primary_key=True, index=True)

Base.metadata.create_all(engine, checkfirst=True)

#############################################
# 2) FUNÇÃO GLOBAL DE CHECAGEM DE ADMIN
#############################################
async def admin_or_owner_check(interaction: discord.Interaction) -> bool:
    """
    Retorna True se o usuário for dono do servidor ou tiver permissão de administrador.
    """
    if not interaction.guild:
        return False
    return (
        interaction.user.id == interaction.guild.owner_id
        or interaction.user.guild_permissions.administrator
    )

#############################################
# 3) NOVO SISTEMA DE CUSTOMIZAÇÃO VIA BOTÃO
#############################################
class TicketBuilderModal(Modal, title="Personalização do Ticket"):
    """
    Modal que coleta informações para customizar o embed do ticket.
    """
    title_input = TextInput(
        label="Título do Ticket",
        placeholder="Digite o título desejado",
        required=True
    )
    description_input = TextInput(
        label="Descrição do Ticket",
        style=discord.TextStyle.long,
        placeholder="Digite a descrição",
        required=True
    )
    image_url_input = TextInput(
        label="URL da Imagem/GIF (opcional)",
        placeholder="https://...",
        required=False
    )
    support_roles_input = TextInput(
        label="Cargos de Suporte (IDs separados por vírgula)",
        placeholder="Ex: 1234567890,0987654321",
        required=False
    )
    logs_channel_input = TextInput(
        label="Canal de Logs (ID, opcional)",
        placeholder="Ex: 11223344556677",
        required=False
    )
    evaluation_channel_input = TextInput(
        label="Canal de Avaliação (ID, opcional)",
        placeholder="Ex: 99887766554433",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        """
        Ao enviar o modal, exibimos um embed de pré-visualização ephemeral.
        Se quiser salvar no banco, descomente a parte de session.commit().
        """
        # Verifica admin
        if not await admin_or_owner_check(interaction):
            return await interaction.response.send_message(
                "❌ Somente administradores podem personalizar o embed.",
                ephemeral=True
            )

        # Caso deseje salvar no banco:
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=str(interaction.guild.id)).first()
            if not settings:
                settings = TicketGuildSettings(
                    guild_id=str(interaction.guild.id),
                    custom_ticket_settings={},
                    support_roles=[],
                    logs_channel="",
                    evaluation_channel=""
                )
                session.add(settings)

            settings.custom_ticket_settings = {
                "title": self.title_input.value,
                "description": self.description_input.value,
                "image_url": self.image_url_input.value
            }
            # Converte cargos de suporte para lista de int
            if self.support_roles_input.value:
                try:
                    role_ids = [int(r.strip()) for r in self.support_roles_input.value.split(",") if r.strip().isdigit()]
                    settings.support_roles = role_ids
                except Exception:
                    return await interaction.response.send_message("❌ Erro ao processar os IDs dos cargos.", ephemeral=True)

            settings.logs_channel = self.logs_channel_input.value or ""
            settings.evaluation_channel = self.evaluation_channel_input.value or ""

            session.commit()

        # Monta embed de pré-visualização
        embed = discord.Embed(
            title=self.title_input.value,
            description=self.description_input.value,
            color=discord.Color.blue()
        )
        if self.image_url_input.value:
            embed.set_image(url=self.image_url_input.value)

        embed.add_field(
            name="Cargos de Suporte",
            value=self.support_roles_input.value or "Nenhum",
            inline=False
        )
        embed.add_field(
            name="Canal de Logs",
            value=self.logs_channel_input.value or "Nenhum",
            inline=False
        )
        embed.add_field(
            name="Canal de Avaliação",
            value=self.evaluation_channel_input.value or "Nenhum",
            inline=False
        )

        await interaction.response.send_message(
            "✅ Configurações atualizadas! Veja a pré-visualização abaixo:",
            embed=embed,
            ephemeral=True
        )

class TicketBuilderView(View):
    """
    Exibe um botão que, ao ser clicado, abre o modal de customização do ticket.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Customizar Ticket", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketBuilderModal())

#############################################
# 4) VIEWS E MODAIS DO SISTEMA DE TICKETS
#############################################
class TicketPanelView(View):
    """
    Exibe selects (tipo de problema e prioridade) para criar o ticket.
    """
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.problem_type = None
        self.priority = None
        self.ticket_created = False

        self.problem_select = Select(
            placeholder="Escolha um tipo de problema...",
            options=[
                discord.SelectOption(label="Problema Técnico", value="Problema Técnico"),
                discord.SelectOption(label="Denúncia", value="Denúncia"),
                discord.SelectOption(label="Dúvidas", value="Dúvidas")
            ],
            custom_id="ticket_problem"
        )
        self.priority_select = Select(
            placeholder="Escolha a prioridade...",
            options=[
                discord.SelectOption(label="Baixa", value="Baixa"),
                discord.SelectOption(label="Média", value="Média"),
                discord.SelectOption(label="Alta", value="Alta"),
                discord.SelectOption(label="Urgente", value="Urgente")
            ],
            custom_id="ticket_priority"
        )
        self.add_item(self.problem_select)
        self.add_item(self.priority_select)

        self.problem_select.callback = self.problem_callback
        self.priority_select.callback = self.priority_callback

    async def problem_callback(self, interaction: discord.Interaction):
        self.problem_type = self.problem_select.values[0]
        await interaction.response.send_message(f"Problema selecionado: {self.problem_type}", ephemeral=True)
        await self.check_and_create_ticket(interaction)

    async def priority_callback(self, interaction: discord.Interaction):
        self.priority = self.priority_select.values[0]
        await interaction.response.send_message(f"Prioridade selecionada: {self.priority}", ephemeral=True)
        await self.check_and_create_ticket(interaction)

    async def check_and_create_ticket(self, interaction: discord.Interaction):
        if self.problem_type and self.priority and not self.ticket_created:
            self.ticket_created = True
            await self.cog.create_ticket_channel(interaction, self.problem_type, self.priority)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception as e:
                print(f"[TicketPanelView] Erro ao editar a mensagem do painel: {e}")

class TicketChannelView(View):
    def __init__(self, ticket_channel, owner_id):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.owner_id = owner_id
        self.add_item(Button(label="Fechar Ticket", style=discord.ButtonStyle.danger, custom_id=f"close_{ticket_channel.id}"))
        self.add_item(Button(label="Chamar Moderador", style=discord.ButtonStyle.primary, custom_id=f"call_mod_{ticket_channel.id}"))
        self.add_item(Button(label="Marcar como Em Análise", style=discord.ButtonStyle.secondary, custom_id=f"status_{ticket_channel.id}"))

#############################################
# 5) COG PRINCIPAL DO SISTEMA DE TICKETS
#############################################
class TicketCog(commands.Cog, name="TicketCog"):
    """Sistema de Tíquetes com Personalização Completa (Banco de Dados)."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category_name = "Tickets"
        self.ticket_owners = {}  # canal_id -> user_id
        print("[TicketCog] Iniciado.")

    def get_guild_settings(self, guild_id: str) -> TicketGuildSettings:
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=guild_id).first()
            if not settings:
                settings = TicketGuildSettings(
                    guild_id=guild_id,
                    custom_ticket_settings={},
                    support_roles=[],
                    logs_channel="",
                    evaluation_channel=""
                )
                session.add(settings)
                session.commit()
            return settings

    def get_user_data(self, user_id: str) -> TicketUserData:
        with SessionLocal() as session:
            user_data = session.query(TicketUserData).filter_by(user_id=user_id).first()
            if not user_data:
                user_data = TicketUserData(user_id=user_id, ticket_count=0, open_tickets=0)
                session.add(user_data)
                session.commit()
            return user_data

    async def create_ticket_channel(self, interaction: discord.Interaction, problem_type: str, priority: str):
        guild_id_str = str(interaction.guild.id)
        user_id_str = str(interaction.user.id)

        # Verifica se o usuário está bloqueado
        with SessionLocal() as session:
            if session.query(BlacklistedUser).filter_by(user_id=user_id_str).first():
                return await interaction.response.send_message("❌ Você não tem permissão para abrir tickets.", ephemeral=True)

        # Verifica/atualiza dados do usuário
        with SessionLocal() as session:
            user_data = session.query(TicketUserData).filter_by(user_id=user_id_str).first()
            if not user_data:
                user_data = TicketUserData(user_id=user_id_str, ticket_count=0, open_tickets=0)
                session.add(user_data)
                session.commit()

            if user_data.open_tickets >= 3:
                return await interaction.response.send_message("⚠️ Você já tem 3 tickets abertos. Feche um antes de abrir outro.", ephemeral=True)

            user_data.ticket_count += 1
            user_data.open_tickets += 1
            session.commit()
            ticket_number = user_data.ticket_count

        # Pega configurações da guild
        settings = self.get_guild_settings(guild_id_str)

        # Cria ou obtém a categoria de tickets
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.ticket_category_name)
        if not category:
            category = await guild.create_category(self.ticket_category_name)

        # Define permissões
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_messages=True)
        }
        for role_id in settings.support_roles:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Cria o canal
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}-{ticket_number}",
            category=category,
            overwrites=overwrites
        )
        self.ticket_owners[str(ticket_channel.id)] = interaction.user.id

        # Cria o embed
        embed = discord.Embed(
            title=settings.custom_ticket_settings.get("title", f"📩 Ticket #{ticket_number} - {problem_type}"),
            description=settings.custom_ticket_settings.get("description", "Seu atendimento foi iniciado. Aguarde um moderador."),
            color=discord.Color.blue()
        )
        embed.add_field(name="🎖️ Prioridade", value=priority, inline=True)
        embed.add_field(name="Status", value="Aberto", inline=True)
        if settings.custom_ticket_settings.get("image_url"):
            embed.set_image(url=settings.custom_ticket_settings["image_url"])

        view = TicketChannelView(ticket_channel, interaction.user.id)
        await ticket_channel.send(content=f"{interaction.user.mention} seu ticket foi criado!", embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket criado! Acesse {ticket_channel.mention}", ephemeral=True)

        # Log em canal de logs (se configurado)
        if settings.logs_channel:
            logs_channel = guild.get_channel(int(settings.logs_channel))
            if logs_channel:
                await logs_channel.send(
                    f"📜 Ticket criado por {interaction.user.mention} - Prioridade: {priority} - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )

    ########################################################
    # 6) COMANDOS DE CONFIG: /setup_ticket, /ticket_builder
    ########################################################

    # 6.1) Comando para criar painel de tickets
    @app_commands.check(admin_or_owner_check)
    @app_commands.command(name="setup_ticket", description="Cria um painel de tickets interativo (apenas admin/owner).")
    async def setup_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📩 Criar um Ticket",
            description="Escolha o tipo de problema e a prioridade do atendimento.",
            color=discord.Color.green()
        )
        view = TicketPanelView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel de tickets configurado!", ephemeral=True)

    # 6.2) Comando para abrir o “Ticket Builder” (botão + modal)
    @app_commands.check(admin_or_owner_check)
    @app_commands.command(name="ticket_builder", description="Abre um painel para customizar o embed do ticket (apenas admin/owner).")
    async def ticket_builder(self, interaction: discord.Interaction):
        """
        Responde ephemeral com um botão. Ao clicar, abre o modal de customização.
        """
        view = TicketBuilderView()
        await interaction.response.send_message(
            "Clique no botão abaixo para customizar o sistema de tickets:",
            view=view,
            ephemeral=True
        )

    # (Opcional) Comando para configurar parâmetros de forma direta
    @app_commands.check(admin_or_owner_check)
    @app_commands.command(name="config_ticket", description="Configura parâmetros básicos (apenas admin/owner).")
    async def config_ticket(self, interaction: discord.Interaction, setting: str, value: str):
        """
        Exemplos de setting:
          - title, description, image_url
          - support_roles (IDs separados por vírgula)
          - logs_channel (ID do canal)
          - evaluation_channel (ID do canal)
        """
        guild_id = str(interaction.guild.id)
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=guild_id).first()
            if not settings:
                settings = TicketGuildSettings(
                    guild_id=guild_id,
                    custom_ticket_settings={},
                    support_roles=[],
                    logs_channel="",
                    evaluation_channel=""
                )
                session.add(settings)

            if setting in ["title", "description", "image_url"]:
                cts = settings.custom_ticket_settings or {}
                cts[setting] = value
                settings.custom_ticket_settings = cts
            elif setting == "support_roles":
                roles = [int(role_id.strip()) for role_id in value.split(",") if role_id.strip().isdigit()]
                settings.support_roles = roles
            elif setting == "logs_channel":
                settings.logs_channel = value
            elif setting == "evaluation_channel":
                settings.evaluation_channel = value
            else:
                return await interaction.response.send_message("⚠️ Configuração inválida.", ephemeral=True)

            session.commit()

        await interaction.response.send_message("✅ Configuração atualizada!", ephemeral=True)

    #############################################
    # 7) LISTENER PARA BOTÕES E INTERAÇÕES
    #############################################
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            # Fechar ticket
            if custom_id.startswith("close_"):
                channel_id = int(custom_id.split("_")[1])
                channel = self.bot.get_channel(channel_id)
                if channel:
                    owner_id = self.ticket_owners.get(str(channel_id))
                    settings = self.get_guild_settings(str(interaction.guild.id))
                    if (interaction.user.id != owner_id and 
                        not any(role.id in settings.support_roles for role in interaction.user.roles)):
                        return await interaction.response.send_message("❌ Você não tem permissão para fechar este ticket.", ephemeral=True)
                    try:
                        await channel.delete()
                        if owner_id:
                            user_id_str = str(owner_id)
                            with SessionLocal() as session:
                                user_data = session.query(TicketUserData).filter_by(user_id=user_id_str).first()
                                if user_data and user_data.open_tickets > 0:
                                    user_data.open_tickets -= 1
                                    session.commit()
                        if str(channel_id) in self.ticket_owners:
                            del self.ticket_owners[str(channel_id)]
                        await interaction.response.send_message("🔒 Ticket fechado com sucesso!", ephemeral=True)
                    except Exception as e:
                        await interaction.response.send_message("❌ Erro ao fechar o ticket.", ephemeral=True)
                        print(f"[on_interaction:close_] Erro ao fechar ticket:
