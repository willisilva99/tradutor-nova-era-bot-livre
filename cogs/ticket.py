import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from datetime import datetime
import asyncio
import os

# IMPORTAÇÃO DO SQLALCHEMY
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSON

# CONFIGURAÇÃO DO BANCO DE DADOS
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERRO: A variável de ambiente DATABASE_URL não está definida.")

engine = create_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# MODELOS DE DADOS

class TicketUserData(Base):
    """
    Armazena dados por usuário:
      - ticket_count: total de tickets criados
      - open_tickets: tickets abertos atualmente
    """
    __tablename__ = "ticket_user_data"
    user_id = Column(String, primary_key=True, index=True)
    ticket_count = Column(Integer, default=0)
    open_tickets = Column(Integer, default=0)

class TicketGuildSettings(Base):
    """
    Armazena configurações por guild:
      - custom_ticket_settings: configurações customizadas do embed (título, descrição, imagem)
      - support_roles: lista de IDs de cargos autorizados a responder
      - logs_channel: ID do canal de logs
      - evaluation_channel: ID do canal de avaliação
    """
    __tablename__ = "ticket_guild_settings"
    guild_id = Column(String, primary_key=True, index=True)
    custom_ticket_settings = Column(JSON, nullable=True, default={})
    support_roles = Column(JSON, nullable=True, default=[])  # lista de inteiros (IDs)
    logs_channel = Column(String, nullable=True)
    evaluation_channel = Column(String, nullable=True)

class BlacklistedUser(Base):
    """
    Armazena os usuários que não podem abrir tickets.
    """
    __tablename__ = "blacklisted_users"
    user_id = Column(String, primary_key=True, index=True)

# Cria as tabelas se não existirem
Base.metadata.create_all(engine, checkfirst=True)

# VIEWS E MODAIS DO BOT

class TicketChannelView(View):
    def __init__(self, ticket_channel, owner_id):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.owner_id = owner_id
        self.add_item(Button(label="Fechar Ticket", style=discord.ButtonStyle.danger, custom_id=f"close_{ticket_channel.id}"))
        self.add_item(Button(label="Chamar Moderador", style=discord.ButtonStyle.primary, custom_id=f"call_mod_{ticket_channel.id}"))
        self.add_item(Button(label="Marcar como Em Análise", style=discord.ButtonStyle.secondary, custom_id=f"status_{ticket_channel.id}"))

class TicketPanelView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.problem_type = None
        self.priority = None

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
        if self.problem_type and self.priority:
            await self.cog.create_ticket_channel(interaction, self.problem_type, self.priority)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception as e:
                print(f"Erro ao editar a mensagem do painel: {e}")

class TicketEmbedCustomizationModal(Modal, title="Customização do Ticket"):
    title_input = TextInput(label="Título do Ticket", placeholder="Digite o título desejado", required=True)
    description_input = TextInput(label="Descrição do Ticket", placeholder="Digite a descrição", style=discord.TextStyle.long, required=True)
    image_url_input = TextInput(label="URL da Imagem/GIF", placeholder="Link para imagem ou GIF (opcional)", required=False)
    logs_channel_input = TextInput(label="Canal de Logs (ID)", placeholder="Digite o ID do canal de logs", required=True)
    evaluation_channel_input = TextInput(label="Canal de Avaliação (ID)", placeholder="Digite o ID do canal de avaliação", required=True)
    support_roles_input = TextInput(label="Cargos de Suporte (IDs separados por vírgula)", placeholder="Ex: 1234567890,0987654321", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cog: TicketCog = interaction.client.get_cog("TicketCog")
        if not cog:
            return await interaction.response.send_message("❌ Erro interno: Cog não encontrado.", ephemeral=True)
        
        # Atualiza as configurações da guilda no banco
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
            settings.custom_ticket_settings = {
                "title": self.title_input.value,
                "description": self.description_input.value,
                "image_url": self.image_url_input.value
            }
            settings.logs_channel = self.logs_channel_input.value
            settings.evaluation_channel = self.evaluation_channel_input.value
            try:
                roles = [int(role_id.strip()) for role_id in self.support_roles_input.value.split(",") if role_id.strip().isdigit()]
                settings.support_roles = roles
            except Exception as e:
                return await interaction.response.send_message("❌ Erro ao processar os IDs dos cargos.", ephemeral=True)
            session.commit()

        embed = discord.Embed(
            title=self.title_input.value,
            description=self.description_input.value,
            color=discord.Color.blue()
        )
        if self.image_url_input.value:
            embed.set_image(url=self.image_url_input.value)
        embed.add_field(name="🎖️ Prioridade", value="Ex: Baixa/Média/Alta/Urgente", inline=True)
        embed.add_field(name="Status", value="Ex: Aberto/Em Análise/Fechado", inline=True)
        
        await interaction.response.send_message("✅ Configurações atualizadas! Veja a pré-visualização abaixo:", embed=embed, ephemeral=True)

# TICKET COG COM INTEGRAÇÃO AO BANCO DE DADOS

class TicketCog(commands.Cog, name="TicketCog"):
    """Sistema Avançado de Tíquetes com Personalização Completa usando Banco de Dados."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category_name = "Tickets"
        # Mapeamento temporário de canal de ticket para o ID do dono (não persistido)
        self.ticket_owners = {}

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
        try:
            user_id_str = str(interaction.user.id)
            # Verifica se o usuário está bloqueado
            with SessionLocal() as session:
                if session.query(BlacklistedUser).filter_by(user_id=user_id_str).first():
                    return await interaction.response.send_message("❌ Você não tem permissão para abrir tickets.", ephemeral=True)
            
            # Recupera ou cria os dados do usuário
            with SessionLocal() as session:
                user_data = session.query(TicketUserData).filter_by(user_id=user_id_str).first()
                if not user_data:
                    user_data = TicketUserData(user_id=user_id_str, ticket_count=0, open_tickets=0)
                    session.add(user_data)
                    session.commit()
                if user_data.open_tickets >= 3:
                    return await interaction.response.send_message("⚠️ Você já tem 3 tickets abertos. Feche um antes de abrir outro.", ephemeral=True)
                # Incrementa contadores
                user_data.ticket_count += 1
                user_data.open_tickets += 1
                session.commit()
                ticket_number = user_data.ticket_count

            guild = interaction.guild
            settings = self.get_guild_settings(str(guild.id))
            
            # Obtém ou cria a categoria de tickets
            category = discord.utils.get(guild.categories, name=self.ticket_category_name)
            if not category:
                category = await guild.create_category(self.ticket_category_name)
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_messages=True)
            }
            support_role_ids = settings.support_roles if settings.support_roles else []
            for role_id in support_role_ids:
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}-{ticket_number}",
                category=category,
                overwrites=overwrites
            )
            self.ticket_owners[str(ticket_channel.id)] = interaction.user.id
            
            embed = discord.Embed(
                title=settings.custom_ticket_settings.get("title", f"📩 Ticket #{ticket_number} - {problem_type}"),
                description=settings.custom_ticket_settings.get("description", "Seu atendimento foi iniciado. Aguarde um moderador."),
                color=discord.Color.blue()
            )
            embed.add_field(name="🎖️ Prioridade", value=priority, inline=True)
            embed.add_field(name="Status", value="Aberto", inline=True)
            if settings.custom_ticket_settings.get("image_url"):
                embed.set_image(url=settings.custom_ticket_settings.get("image_url"))
            
            view = TicketChannelView(ticket_channel, interaction.user.id)
            await ticket_channel.send(content=f"{interaction.user.mention} seu ticket foi criado!", embed=embed, view=view)
            await interaction.response.send_message(f"✅ Ticket criado! Acesse {ticket_channel.mention}", ephemeral=True)
            
            # Registra log, se configurado
            if settings.logs_channel:
                logs_channel = guild.get_channel(int(settings.logs_channel))
                if logs_channel:
                    await logs_channel.send(
                        f"📜 Ticket criado por {interaction.user.mention} - Prioridade: {priority} - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
        except Exception as e:
            await interaction.response.send_message("❌ Ocorreu um erro ao criar o ticket.", ephemeral=True)
            print(f"Erro ao criar ticket: {e}")

    @app_commands.command(name="setup_ticket", description="🎫 Configura um painel de tickets interativo.")
    async def setup_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📩 Criar um Ticket",
            description="Escolha o tipo de problema e a prioridade do atendimento.",
            color=discord.Color.green()
        )
        view = TicketPanelView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel de tickets configurado!", ephemeral=True)
    
    @app_commands.command(name="config_ticket", description="Configura definições básicas dos tickets.")
    async def config_ticket(self, interaction: discord.Interaction, setting: str, value: str):
        """
        Configura parâmetros básicos.
        Exemplos de setting:
          - title, description, image_url (custom_ticket_settings)
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
    
    @app_commands.command(name="customize_ticket_embed", description="Personalize o embed do ticket via painel interativo.")
    async def customize_ticket_embed(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketEmbedCustomizationModal())
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("close_"):
                channel_id = int(custom_id.split("_")[1])
                channel = self.bot.get_channel(channel_id)
                if channel:
                    owner_id = self.ticket_owners.get(str(channel_id))
                    # Verifica se o usuário é o dono ou tem cargo de suporte
                    settings = self.get_guild_settings(str(interaction.guild.id))
                    if interaction.user.id != owner_id and not any(role.id in settings.support_roles for role in interaction.user.roles):
                        return await interaction.response.send_message("❌ Você não tem permissão para fechar este ticket.", ephemeral=True)
                    try:
                        await channel.delete()
                        # Atualiza os dados do usuário para reduzir o contador de tickets abertos
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
                        print(f"Erro ao fechar ticket: {e}")
            elif custom_id.startswith("call_mod_"):
                try:
                    await interaction.response.send_message("🔔 Um moderador foi chamado para este ticket!", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message("❌ Erro ao chamar o moderador.", ephemeral=True)
                    print(f"Erro ao chamar moderador: {e}")
            elif custom_id.startswith("status_"):
                try:
                    channel_id = int(custom_id.split("_")[1])
                    channel = self.bot.get_channel(channel_id)
                    async for message in channel.history(limit=20):
                        if message.embeds:
                            embed = message.embeds[0]
                            embed_dict = embed.to_dict()
                            new_fields = []
                            updated = False
                            for field in embed_dict.get("fields", []):
                                if field["name"] == "Status":
                                    new_fields.append({"name": "Status", "value": "Em Análise", "inline": True})
                                    updated = True
                                else:
                                    new_fields.append(field)
                            if not updated:
                                new_fields.append({"name": "Status", "value": "Em Análise", "inline": True})
                            embed_dict["fields"] = new_fields
                            new_embed = discord.Embed.from_dict(embed_dict)
                            await message.edit(embed=new_embed)
                            break
                    await interaction.response.send_message("✅ O ticket agora está marcado como 'Em Análise'.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message("❌ Erro ao atualizar o status do ticket.", ephemeral=True)
                    print(f"Erro ao atualizar status: {e}")

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
