import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from datetime import datetime, timezone
import asyncio
import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSON

# Configuração do Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL não configurada")

engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelos do Banco de Dados
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

# Modal de Personalização
class TicketBuilderModal(Modal, title="Personalização do Ticket"):
    title_input = TextInput(
        label="Título do Ticket",
        placeholder="Sistema de Tickets",
        required=True,
        max_length=256
    )
    
    description_input = TextInput(
        label="Descrição do Ticket",
        style=discord.TextStyle.paragraph,
        placeholder="Descreva seu problema...",
        required=True,
        max_length=2000
    )
    
    emoji_input = TextInput(
        label="Emoji do Título",
        placeholder="🎫",
        required=False,
        max_length=2
    )
    
    color_input = TextInput(
        label="Cor do Embed (hex)",
        placeholder="#3498db",
        required=False,
        max_length=7
    )
    
    footer_input = TextInput(
        label="Texto do Rodapé",
        placeholder="Atendimento 24/7",
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Converte cor hex para int
            color = int(self.color_input.value.strip('#'), 16) if self.color_input.value else 0x3498db
            
            # Monta configurações
            settings_data = {
                "title": f"{self.emoji_input.value} {self.title_input.value}" if self.emoji_input.value else self.title_input.value,
                "description": self.description_input.value,
                "color": color,
                "footer": self.footer_input.value,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Salva no banco
            with SessionLocal() as session:
                settings = session.query(TicketGuildSettings).filter_by(guild_id=str(interaction.guild.id)).first()
                if not settings:
                    settings = TicketGuildSettings(
                        guild_id=str(interaction.guild.id),
                        custom_ticket_settings={},
                        support_roles=[],
                    )
                    session.add(settings)
                
                settings.custom_ticket_settings = settings_data
                session.commit()

            # Preview do embed
            embed = discord.Embed(
                title=settings_data["title"],
                description=settings_data["description"],
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            
            if settings_data.get("footer"):
                embed.set_footer(text=settings_data["footer"])

            await interaction.response.send_message(
                "✅ Personalização do ticket atualizada!\nPreview:",
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"Erro na personalização: {e}")
            await interaction.response.send_message(
                "❌ Erro ao salvar as configurações!",
                ephemeral=True
            )

# View do Botão de Personalização
class TicketBuilderView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Personalizar Ticket",
        style=discord.ButtonStyle.primary,
        emoji="⚙️"
    )
    async def customize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketBuilderModal())

# View do Painel de Tickets
class TicketPanelView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.problem_type = None
        self.priority = None

        # Seletor de Tipo
        self.add_item(Select(
            custom_id="ticket_type",
            placeholder="Selecione o tipo de ticket",
            options=[
                discord.SelectOption(label="Suporte", value="support", emoji="🛠️"),
                discord.SelectOption(label="Dúvida", value="question", emoji="❓"),
                discord.SelectOption(label="Sugestão", value="suggestion", emoji="💡"),
                discord.SelectOption(label="Reportar Problema", value="report", emoji="🚨")
            ]
        ))

        # Seletor de Prioridade
        self.add_item(Select(
            custom_id="priority",
            placeholder="Selecione a prioridade",
            options=[
                discord.SelectOption(label="Baixa", value="low", emoji="🟢"),
                discord.SelectOption(label="Média", value="medium", emoji="🟡"),
                discord.SelectOption(label="Alta", value="high", emoji="🟠"),
                discord.SelectOption(label="Urgente", value="urgent", emoji="🔴")
            ]
        ))

    @discord.ui.select(custom_id="ticket_type")
    async def type_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.problem_type = select.values[0]
        await interaction.response.defer()
        if self.priority:
            await self.create_ticket(interaction)

    @discord.ui.select(custom_id="priority")
    async def priority_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.priority = select.values[0]
        await interaction.response.defer()
        if self.problem_type:
            await self.create_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction):
        await self.cog.create_ticket(
            interaction,
            self.problem_type,
            self.priority,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        )

# Cog Principal
class TicketCog(commands.Cog, name="Tickets"):
    def __init__(self, bot):
        self.bot = bot
        self.tickets_category = "Tickets"
        print("✅ Sistema de Tickets iniciado!")

    @app_commands.command(
        name="ticket_builder",
        description="Abre o personalizador de tickets"
    )
    @app_commands.default_permissions(administrator=True)
    async def ticket_builder(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Clique abaixo para personalizar o sistema de tickets:",
            view=TicketBuilderView(),
            ephemeral=True
        )

    @app_commands.command(
        name="setup_ticket",
        description="Configura o painel de tickets no canal"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_ticket(self, interaction: discord.Interaction):
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=str(interaction.guild.id)).first()
            custom_settings = settings.custom_ticket_settings if settings else {}

        embed = discord.Embed(
            title=custom_settings.get("title", "🎫 Sistema de Tickets"),
            description=custom_settings.get("description", "Selecione o tipo e a prioridade do seu ticket abaixo."),
            color=custom_settings.get("color", 0x3498db),
            timestamp=datetime.now(timezone.utc)
        )

        if custom_settings.get("footer"):
            embed.set_footer(text=custom_settings["footer"])

        await interaction.channel.send(embed=embed, view=TicketPanelView(self))
        await interaction.response.send_message("✅ Painel configurado!", ephemeral=True)

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str, priority: str, timestamp: str):
        # Verifica categoria
        category = discord.utils.get(interaction.guild.categories, name=self.tickets_category)
        if not category:
            category = await interaction.guild.create_category(self.tickets_category)

        # Nome do canal
        channel_name = f"ticket-{interaction.user.name}-{ticket_type}"

        # Cria o canal
        ticket_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category
        )

        # Configurações do ticket
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=str(interaction.guild.id)).first()
            custom_settings = settings.custom_ticket_settings if settings else {}

        # Cria o embed
        embed = discord.Embed(
            title=custom_settings.get("title", "🎫 Novo Ticket"),
            description=custom_settings.get("description", "Ticket criado com sucesso!"),
            color=custom_settings.get("color", 0x3498db),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="Usuário", value=interaction.user.mention, inline=True)
        embed.add_field(name="Tipo", value=ticket_type, inline=True)
        embed.add_field(name="Prioridade", value=priority, inline=True)
        embed.add_field(name="Data/Hora", value=timestamp, inline=False)

        if custom_settings.get("footer"):
            embed.set_footer(text=custom_settings["footer"])

        await ticket_channel.send(
            f"{interaction.user.mention} seu ticket foi criado!",
            embed=embed
        )

        await interaction.followup.send(
            f"✅ Ticket criado com sucesso! Acesse: {ticket_channel.mention}",
            ephemeral=True
        )

def setup(bot):
    bot.add_cog(TicketCog(bot))
