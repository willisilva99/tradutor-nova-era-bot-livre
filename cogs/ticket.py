import discord
import random
import string
from discord.ext import commands
from discord import app_commands
from db import SessionLocal, get_or_create_guild_ticket_config  # Ajuste o import conforme seu projeto

def gerar_codigo_ticket(tamanho=6):
    """Gera um código aleatório (ex.: ABC123) para identificar o ticket."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(tamanho))

class AbrirTicketModal(discord.ui.Modal):
    """Modal para o usuário descrever o motivo do ticket."""
    def __init__(self, bot: commands.Bot, config_db, cargo_staff_id: str, logs_id: str, category_id: str):
        super().__init__(title="Abrir Ticket")
        self.bot = bot
        self.config_db = config_db      # Objeto do banco (GuildTicketConfig)
        self.cargo_staff_id = cargo_staff_id
        self.logs_id = logs_id
        self.category_id = category_id

        self.motivo = discord.ui.TextInput(
            label="Descreva o motivo do seu ticket",
            style=discord.TextStyle.long,
            placeholder="Ex: Preciso de ajuda com XYZ...",
            required=True
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        """Ao enviar o modal, criamos o canal de ticket e enviamos a view com botões."""
        code = gerar_codigo_ticket()
        guild = interaction.guild

        # Cargo Staff (pode ser None se não estiver configurado)
        staff_role = guild.get_role(int(self.cargo_staff_id)) if self.cargo_staff_id else None
        logs_channel = guild.get_channel(int(self.logs_id)) if self.logs_id else None
        category_channel = guild.get_channel(int(self.category_id)) if self.category_id else None

        # Permissões do canal
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Cria o canal (text_channel) na categoria (se existir)
        channel_name = f"ticket-{interaction.user.name}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category_channel,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user} | Código: {code}"
        )

        # Monta o embed inicial no canal
        description = (
            f"**Usuário:** {interaction.user.mention}\n"
            f"**Motivo:** {self.motivo.value}\n"
            f"**Código:** `{code}`\n"
            "Ninguém assumiu ainda."
        )
        embed = discord.Embed(title="Ticket Aberto", description=description, color=discord.Color.blue())

        # Cria a View com botões do ticket
        view = TicketChannelView(
            autor_ticket=interaction.user,
            staff_role=staff_role,
            code=code,
            logs_channel=logs_channel
        )

        await ticket_channel.send(
            content=f"{interaction.user.mention} {'||' + staff_role.mention + '||' if staff_role else ''}",
            embed=embed,
            view=view
        )

        # Manda log no canal de logs, se existir
        if logs_channel:
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
            await logs_channel.send(embed=log_embed)

        # Confirmação para o usuário
        await interaction.response.send_message(
            f"Seu ticket foi criado: {ticket_channel.mention}",
            ephemeral=True
        )

class TicketChannelView(discord.ui.View):
    """View com botões de controle do ticket dentro do canal."""
    def __init__(self, autor_ticket: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor_ticket = autor_ticket
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.success, custom_id="ticket_assumir")
    async def ticket_assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Staff clica para assumir o ticket."""
        # Verifica se o usuário é staff
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Apenas usuários com o cargo Staff podem assumir este ticket.",
                ephemeral=True
            )
            return

        # Edita a embed para mostrar quem assumiu
        msg = interaction.message
        if msg and msg.embeds:
            embed_atual = msg.embeds[0]
            desc = embed_atual.description
            if "Ninguém assumiu ainda." in desc:
                desc = desc.replace("Ninguém assumiu ainda.", f"Ticket assumido por {interaction.user.mention}.")
            else:
                # Se quiser substituir qualquer outro staff, vá adaptando
                desc += f"\nAssumido por {interaction.user.mention}."
            new_embed = discord.Embed(title=embed_atual.title, description=desc, color=discord.Color.blue())
            if embed_atual.thumbnail:
                new_embed.set_thumbnail(url=embed_atual.thumbnail.url)
            if embed_atual.image:
                new_embed.set_image(url=embed_atual.image.url)

            await msg.edit(embed=new_embed, view=self)

        await interaction.response.send_message("Você assumiu este ticket.", ephemeral=True)

        # Log
        if self.logs_channel:
            await self.logs_channel.send(
                embed=discord.Embed(
                    title="Ticket Assumido",
                    description=(
                        f"**Canal:** {interaction.channel.mention}\n"
                        f"**Assumido por:** {interaction.user.mention}\n"
                        f"**Código:** {self.code}"
                    ),
                    color=discord.Color.orange()
                )
            )

    @discord.ui.button(label="Sair do Ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_sair")
    async def ticket_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        """O autor do ticket pode se remover do canal."""
        if interaction.user.id != self.autor_ticket.id:
            await interaction.response.send_message(
                "Apenas o autor do ticket pode sair.",
                ephemeral=True
            )
            return

        # Remove permissões do autor
        overwrites = interaction.channel.overwrites
        if interaction.user in overwrites:
            overwrites[interaction.user].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)

        await interaction.response.send_message(
            "Você saiu do ticket. Um staff ainda pode fechar ou continuar aqui.",
            ephemeral=True
        )

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_fechar")
    async def ticket_fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """O staff fecha o ticket e deleta o canal."""
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Apenas o staff pode fechar este ticket!",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Loga no canal de logs
        if self.logs_channel:
            embed = discord.Embed(
                title="Ticket Fechado",
                description=(
                    f"**Canal:** {interaction.channel.mention}\n"
                    f"**Fechado por:** {interaction.user.mention}\n"
                    f"**Código:** {self.code}"
                ),
                color=discord.Color.red()
            )
            await self.logs_channel.send(embed=embed)

        # Dá um tempinho antes de deletar
        await interaction.channel.send("Fechando o ticket em 5 segundos...")
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=5))
        await interaction.channel.delete(reason=f"Ticket fechado por {interaction.user}.")

class TicketPanelView(discord.ui.View):
    """View para mostrar no /ticketpanel, com botão de 'Abrir Ticket'."""
    def __init__(self, bot: commands.Bot, config_db):
        super().__init__(timeout=None)
        self.bot = bot
        self.config_db = config_db  # Objeto GuildTicketConfig do BD

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="botao_abrir_ticket")
    async def botao_abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mostra o modal de abertura de ticket."""
        cargo_staff_id = self.config_db.cargo_staff_id
        logs_id = self.config_db.channel_logs_id
        category_id = self.config_db.category_ticket_id

        modal = AbrirTicketModal(
            bot=self.bot,
            config_db=self.config_db,
            cargo_staff_id=cargo_staff_id or "",
            logs_id=logs_id or "",
            category_id=category_id or ""
        )
        await interaction.response.send_modal(modal)

class TicketCog(commands.Cog):
    """Cog que contém o comando /ticketpanel e gerencia o sistema de tickets."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ticketpanel", description="Cria um painel para abrir tickets.")
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        """Envia um embed com botão para abrir ticket, lendo config do BD."""
        session = SessionLocal()
        try:
            # Carrega ou cria config de tickets da guilda
            guild_id_str = str(interaction.guild_id)
            config_db = get_or_create_guild_ticket_config(session, guild_id_str)

            embed = discord.Embed(
                title="Painel de Tickets",
                description=(
                    "Clique no botão abaixo para abrir um ticket!\n\n"
                    "Se as configurações de cargo/canais não estiverem feitas, o ticket pode não funcionar corretamente."
                ),
                color=discord.Color.blurple()
            )
            view = TicketPanelView(self.bot, config_db)
            await interaction.response.send_message(embed=embed, view=view)
        finally:
            session.close()


async def setup(bot: commands.Bot):
    """Função de setup do cog, chamada no main.py."""
    await bot.add_cog(TicketCog(bot))
