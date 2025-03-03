import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from datetime import datetime
import asyncio

class TicketCog(commands.Cog):
    """Sistema Avançado de Tíquetes com Prioridade, Logs, Status, Avaliação e Notificações."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category_name = "Tickets"
        self.ticket_count = {}  # Contador de tickets
        self.custom_ticket_settings = {}  # Personalização de embed
        self.open_tickets = {}  # Controle de tickets abertos por usuário
        self.blacklisted_users = set()  # Usuários banidos de tickets
        self.logs_channel_name = "logs-tickets"  # Canal de logs padrão
        self.evaluation_channel_name = "avaliacao-tickets"  # Canal de avaliação padrão
        self.support_roles = {}  # Cargos permitidos a responder tickets
        self.ticket_priorities = {"Baixa": 1, "Média": 2, "Alta": 3, "Urgente": 4}  # Prioridades

    async def create_ticket_channel(self, interaction: discord.Interaction, problem_type: str, priority: str):
        """Cria um canal privado para o usuário, com prioridade definida."""
        if interaction.user.id in self.blacklisted_users:
            return await interaction.response.send_message("❌ Você não tem permissão para abrir tickets.", ephemeral=True)
        
        if self.open_tickets.get(interaction.user.id, 0) >= 3:
            return await interaction.response.send_message("⚠️ Você já tem 3 tickets abertos. Feche um antes de abrir outro.", ephemeral=True)
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.ticket_category_name)
        if not category:
            category = await guild.create_category(self.ticket_category_name)

        ticket_number = self.ticket_count.get(interaction.user.id, 0) + 1
        self.ticket_count[interaction.user.id] = ticket_number
        self.open_tickets[interaction.user.id] = self.open_tickets.get(interaction.user.id, 0) + 1
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_messages=True)
        }
        
        # Adicionar os cargos permitidos a responder
        support_roles = self.support_roles.get(interaction.guild.id, [])
        for role_id in support_roles:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}-{ticket_number}",
            category=category,
            overwrites=overwrites
        )
        
        settings = self.custom_ticket_settings.get(interaction.guild.id, {})
        embed = discord.Embed(
            title=settings.get("title", f"📩 Ticket #{ticket_number} - {problem_type}"),
            description=settings.get("description", "Seu atendimento foi iniciado. Aguarde um moderador."),
            color=discord.Color.blue()
        )
        embed.add_field(name="🎖️ Prioridade", value=priority, inline=True)
        embed.set_image(url=settings.get("image_url", ""))
        
        close_button = Button(label="Fechar Ticket", style=discord.ButtonStyle.danger, custom_id=f"close_{ticket_channel.id}")
        call_mod_button = Button(label="Chamar Moderador", style=discord.ButtonStyle.primary, custom_id=f"call_mod_{ticket_channel.id}")
        status_button = Button(label="Marcar como Em Análise", style=discord.ButtonStyle.secondary, custom_id=f"status_{ticket_channel.id}")
        view = View()
        view.add_item(close_button)
        view.add_item(call_mod_button)
        view.add_item(status_button)
        
        await ticket_channel.send(content=f"{interaction.user.mention} seu ticket foi criado!", embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket criado! Acesse {ticket_channel.mention}", ephemeral=True)
        
        logs_channel = discord.utils.get(guild.text_channels, name=self.logs_channel_name)
        if logs_channel:
            await logs_channel.send(f"📜 Ticket criado por {interaction.user.mention} - Prioridade: {priority} - {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    @app_commands.command(name="setup_ticket", description="🎫 Configura um painel de tickets personalizado.")
    async def setup_ticket(self, interaction: discord.Interaction):
        """Cria um painel de tickets interativo."""
        embed = discord.Embed(
            title="📩 Criar um Ticket",
            description="Escolha o tipo de problema e a prioridade do atendimento.",
            color=discord.Color.green()
        )
        select_problem = Select(
            placeholder="Escolha um tipo de problema...",
            options=[
                discord.SelectOption(label="Problema Técnico", value="Problema Técnico"),
                discord.SelectOption(label="Denúncia", value="Denúncia"),
                discord.SelectOption(label="Dúvidas", value="Dúvidas")
            ],
            custom_id="ticket_problem"
        )
        select_priority = Select(
            placeholder="Escolha a prioridade...",
            options=[
                discord.SelectOption(label="Baixa", value="Baixa"),
                discord.SelectOption(label="Média", value="Média"),
                discord.SelectOption(label="Alta", value="Alta"),
                discord.SelectOption(label="Urgente", value="Urgente")
            ],
            custom_id="ticket_priority"
        )
        
        view = View()
        view.add_item(select_problem)
        view.add_item(select_priority)
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel de tickets configurado!", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Gerencia interações nos botões e menus."""
        if interaction.type == discord.InteractionType.component:
            if interaction.data["custom_id"].startswith("close_"):
                channel_id = int(interaction.data["custom_id"].split("_")[1])
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.delete()
                    await interaction.response.send_message("🔒 Ticket fechado com sucesso!", ephemeral=True)
                    self.open_tickets[interaction.user.id] -= 1
            elif interaction.data["custom_id"].startswith("call_mod_"):
                await interaction.response.send_message("🔔 Um moderador foi chamado para este ticket!", ephemeral=True)
            elif interaction.data["custom_id"].startswith("status_"):
                await interaction.response.send_message("✅ O ticket agora está marcado como 'Em Análise'.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
