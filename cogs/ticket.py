import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from datetime import datetime
import asyncio
import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSON

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
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

# Ticket Builder Modal
class TicketBuilderModal(Modal, title="Personalização do Ticket"):
    title_input = TextInput(
        label="Título do Ticket",
        placeholder="Digite o título do ticket",
        required=True,
        max_length=256
    )
    
    description_input = TextInput(
        label="Descrição do Ticket",
        style=discord.TextStyle.paragraph,
        placeholder="Digite a descrição do ticket",
        required=True,
        max_length=2000
    )
    
    color_input = TextInput(
        label="Cor do Embed (hex)",
        placeholder="#3498db",
        required=False,
        max_length=7
    )
    
    image_url_input = TextInput(
        label="URL da Imagem",
        placeholder="https://exemplo.com/imagem.png",
        required=False
    )
    
    footer_text_input = TextInput(
        label="Texto do Rodapé",
        placeholder="Sistema de Tickets v1.0",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Convert hex color to int
            color = int(self.color_input.value.strip('#'), 16) if self.color_input.value else discord.Color.blue().value
            
            # Save to database
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
                    "color": color,
                    "image_url": self.image_url_input.value,
                    "footer_text": self.footer_text_input.value
                }
                session.commit()

            # Create preview embed
            embed = discord.Embed(
                title=self.title_input.value,
                description=self.description_input.value,
                color=color,
                timestamp=datetime.utcnow()
            )
            
            if self.image_url_input.value:
                embed.set_image(url=self.image_url_input.value)
            
            if self.footer_text_input.value:
                embed.set_footer(text=self.footer_text_input.value)

            await interaction.response.send_message(
                "✅ Personalização atualizada! Preview:",
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"Error in ticket customization: {e}")
            await interaction.response.send_message(
                "❌ Erro ao salvar as configurações.",
                ephemeral=True
            )

# Ticket Builder View
class TicketBuilderView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Personalizar Ticket", style=discord.ButtonStyle.primary)
    async def customize_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketBuilderModal())

# Ticket Panel View
class TicketPanelView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.problem_type = None
        self.priority = None
        self.ticket_created = False

        # Add selects
        self.add_item(Select(
            custom_id="problem_type",
            placeholder="Escolha o tipo de problema",
            options=[
                discord.SelectOption(label="Suporte Técnico", value="tech_support"),
                discord.SelectOption(label="Reportar Bug", value="bug_report"),
                discord.SelectOption(label="Sugestão", value="suggestion"),
                discord.SelectOption(label="Outro", value="other")
            ]
        ))
        
        self.add_item(Select(
            custom_id="priority",
            placeholder="Escolha a prioridade",
            options=[
                discord.SelectOption(label="Baixa", value="low"),
                discord.SelectOption(label="Média", value="medium"),
                discord.SelectOption(label="Alta", value="high"),
                discord.SelectOption(label="Urgente", value="urgent")
            ]
        ))

    @discord.ui.select(custom_id="problem_type")
    async def on_problem_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.problem_type = select.values[0]
        await self.check_and_create_ticket(interaction)

    @discord.ui.select(custom_id="priority")
    async def on_priority_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.priority = select.values[0]
        await self.check_and_create_ticket(interaction)

    async def check_and_create_ticket(self, interaction: discord.Interaction):
        if self.problem_type and self.priority and not self.ticket_created:
            self.ticket_created = True
            await self.cog.create_ticket_channel(interaction, self.problem_type, self.priority)
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

# Main Ticket Cog
class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category_name = "Tickets"
        self.ticket_owners = {}
        print("✅ Ticket System initialized")

    @app_commands.command(
        name="ticket_builder",
        description="Personaliza a aparência dos tickets"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_builder(self, interaction: discord.Interaction):
        view = TicketBuilderView()
        await interaction.response.send_message(
            "Clique no botão abaixo para personalizar o sistema de tickets:",
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="setup_ticket",
        description="Configura o painel de tickets"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Sistema de Tickets",
            description="Selecione o tipo de problema e a prioridade para criar um ticket",
            color=discord.Color.blue()
        )
        view = TicketPanelView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel de tickets configurado!", ephemeral=True)

    async def create_ticket_channel(self, interaction: discord.Interaction, problem_type: str, priority: str):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        # Check if user is blacklisted
        with SessionLocal() as session:
            if session.query(BlacklistedUser).filter_by(user_id=user_id).first():
                return await interaction.response.send_message(
                    "❌ Você está impossibilitado de criar tickets.",
                    ephemeral=True
                )

        # Get guild settings
        with SessionLocal() as session:
            settings = session.query(TicketGuildSettings).filter_by(guild_id=guild_id).first()
            custom_settings = settings.custom_ticket_settings if settings else {}

        # Create ticket category if it doesn't exist
        category = discord.utils.get(interaction.guild.categories, name=self.ticket_category_name)
        if not category:
            category = await interaction.guild.create_category(self.ticket_category_name)

        # Create ticket channel
        channel_name = f"ticket-{interaction.user.name}-{len(self.ticket_owners) + 1}"
        ticket_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            topic=f"Ticket criado por {interaction.user.name}"
        )

        # Create ticket embed
        embed = discord.Embed(
            title=custom_settings.get("title", "🎫 Novo Ticket"),
            description=custom_settings.get("description", "Aguarde o atendimento da equipe."),
            color=discord.Color(custom_settings.get("color", discord.Color.blue().value)),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Usuário", value=interaction.user.mention, inline=True)
        embed.add_field(name="Tipo", value=problem_type, inline=True)
        embed.add_field(name="Prioridade", value=priority, inline=True)
        
        if custom_settings.get("image_url"):
            embed.set_image(url=custom_settings["image_url"])
        
        if custom_settings.get("footer_text"):
            embed.set_footer(text=custom_settings["footer_text"])

        # Send initial message in ticket channel
        await ticket_channel.send(
            content=f"{interaction.user.mention} seu ticket foi criado!",
            embed=embed
        )

        # Store ticket owner
        self.ticket_owners[str(ticket_channel.id)] = interaction.user.id

        await interaction.response.send_message(
            f"✅ Ticket criado! Acesse {ticket_channel.mention}",
            ephemeral=True
        )

def setup(bot):
    bot.add_cog(TicketCog(bot))
