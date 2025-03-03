import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
from datetime import datetime
import asyncio
import json
import os

DATA_FILE = "ticket_data.json"

def load_ticket_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    else:
        return {
            "ticket_count": {},
            "open_tickets": {},
            "custom_ticket_settings": {},
            "blacklisted_users": [],
            "support_roles": {}
        }

def save_ticket_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

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

        # Criação dos selects para escolher o problema e a prioridade
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
        # Se as duas opções foram escolhidas, cria o ticket
        if self.problem_type and self.priority:
            await self.cog.create_ticket_channel(interaction, self.problem_type, self.priority)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception as e:
                print(f"Erro ao editar a mensagem do painel: {e}")

class TicketCog(commands.Cog):
    """Sistema Avançado de Tíquetes com Prioridade, Logs, Status, Avaliação e Notificações."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category_name = "Tickets"
        data = load_ticket_data()
        self.ticket_count = data.get("ticket_count", {})
        self.custom_ticket_settings = data.get("custom_ticket_settings", {})
        self.open_tickets = data.get("open_tickets", {})
        self.blacklisted_users = set(data.get("blacklisted_users", []))
        self.support_roles = data.get("support_roles", {})
        self.logs_channel_name = "logs-tickets"
        self.evaluation_channel_name = "avaliacao-tickets"
        self.ticket_priorities = {"Baixa": 1, "Média": 2, "Alta": 3, "Urgente": 4}
        self.ticket_owners = {}  # Mapeia o canal do ticket para o ID do usuário
    
    def save_data(self):
        data = {
            "ticket_count": self.ticket_count,
            "custom_ticket_settings": self.custom_ticket_settings,
            "open_tickets": self.open_tickets,
            "blacklisted_users": list(self.blacklisted_users),
            "support_roles": self.support_roles
        }
        save_ticket_data(data)
    
    async def create_ticket_channel(self, interaction: discord.Interaction, problem_type: str, priority: str):
        """Cria um canal privado para o usuário, com prioridade definida."""
        try:
            if interaction.user.id in self.blacklisted_users:
                return await interaction.response.send_message("❌ Você não tem permissão para abrir tickets.", ephemeral=True)
            
            user_id_str = str(interaction.user.id)
            if self.open_tickets.get(user_id_str, 0) >= 3:
                return await interaction.response.send_message("⚠️ Você já tem 3 tickets abertos. Feche um antes de abrir outro.", ephemeral=True)
            
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name=self.ticket_category_name)
            if not category:
                category = await guild.create_category(self.ticket_category_name)
            
            ticket_number = self.ticket_count.get(user_id_str, 0) + 1
            self.ticket_count[user_id_str] = ticket_number
            self.open_tickets[user_id_str] = self.open_tickets.get(user_id_str, 0) + 1
            self.save_data()
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_messages=True)
            }
            
            # Adiciona os cargos de suporte
            support_roles = self.support_roles.get(str(guild.id), [])
            for role_id in support_roles:
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}-{ticket_number}",
                category=category,
                overwrites=overwrites
            )
            
            # Registra o dono do ticket
            self.ticket_owners[str(ticket_channel.id)] = interaction.user.id
            
            settings = self.custom_ticket_settings.get(str(guild.id), {})
            embed = discord.Embed(
                title=settings.get("title", f"📩 Ticket #{ticket_number} - {problem_type}"),
                description=settings.get("description", "Seu atendimento foi iniciado. Aguarde um moderador."),
                color=discord.Color.blue()
            )
            embed.add_field(name="🎖️ Prioridade", value=priority, inline=True)
            embed.add_field(name="Status", value="Aberto", inline=True)
            if settings.get("image_url"):
                embed.set_image(url=settings.get("image_url"))
            
            view = TicketChannelView(ticket_channel, interaction.user.id)
            
            await ticket_channel.send(content=f"{interaction.user.mention} seu ticket foi criado!", embed=embed, view=view)
            await interaction.response.send_message(f"✅ Ticket criado! Acesse {ticket_channel.mention}", ephemeral=True)
            
            logs_channel = discord.utils.get(guild.text_channels, name=self.logs_channel_name)
            if logs_channel:
                await logs_channel.send(f"📜 Ticket criado por {interaction.user.mention} - Prioridade: {priority} - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        except Exception as e:
            await interaction.response.send_message("❌ Ocorreu um erro ao criar o ticket.", ephemeral=True)
            print(f"Erro ao criar ticket: {e}")
    
    @app_commands.command(name="setup_ticket", description="🎫 Configura um painel de tickets personalizado.")
    async def setup_ticket(self, interaction: discord.Interaction):
        """Cria um painel de tickets interativo."""
        embed = discord.Embed(
            title="📩 Criar um Ticket",
            description="Escolha o tipo de problema e a prioridade do atendimento.",
            color=discord.Color.green()
        )
        view = TicketPanelView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel de tickets configurado!", ephemeral=True)
    
    @app_commands.command(name="config_ticket", description="Configura as definições dos tickets (embed, cargos, etc.).")
    async def config_ticket(self, interaction: discord.Interaction, setting: str, value: str):
        """
        Configura as definições dos tickets.
        Exemplos de setting: title, description, image_url, support_roles (lista separada por vírgula)
        """
        guild_id = str(interaction.guild.id)
        if setting in ["title", "description", "image_url"]:
            if guild_id not in self.custom_ticket_settings:
                self.custom_ticket_settings[guild_id] = {}
            self.custom_ticket_settings[guild_id][setting] = value
        elif setting == "support_roles":
            roles = [int(role_id.strip()) for role_id in value.split(",") if role_id.strip().isdigit()]
            self.support_roles[guild_id] = roles
        else:
            return await interaction.response.send_message("⚠️ Configuração inválida.", ephemeral=True)
        self.save_data()
        await interaction.response.send_message("✅ Configuração atualizada!", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Gerencia interações nos botões e menus dos tickets."""
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("close_"):
                channel_id = int(custom_id.split("_")[1])
                channel = self.bot.get_channel(channel_id)
                if channel:
                    owner_id = self.ticket_owners.get(str(channel_id))
                    # Verifica se o usuário é o dono do ticket ou possui um cargo de suporte
                    if interaction.user.id != owner_id and not any(role.id in self.support_roles.get(str(interaction.guild.id), []) for role in interaction.user.roles):
                        return await interaction.response.send_message("❌ Você não tem permissão para fechar este ticket.", ephemeral=True)
                    try:
                        await channel.delete()
                        # Atualiza a contagem de tickets abertos
                        if owner_id:
                            owner_id_str = str(owner_id)
                            if self.open_tickets.get(owner_id_str, 0) > 0:
                                self.open_tickets[owner_id_str] -= 1
                        if str(channel_id) in self.ticket_owners:
                            del self.ticket_owners[str(channel_id)]
                        self.save_data()
                        await interaction.response.send_message("🔒 Ticket fechado com sucesso!", ephemeral=True)
                    except Exception as e:
                        await interaction.response.send_message("❌ Erro ao fechar o ticket.", ephemeral=True)
                        print(f"Erro ao fechar ticket: {e}")
            elif custom_id.startswith("call_mod_"):
                try:
                    await interaction.response.send_message("🔔 Um moderador foi chamado para este ticket!", ephemeral=True)
                    # Aqui você pode implementar a notificação para um cargo específico
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
