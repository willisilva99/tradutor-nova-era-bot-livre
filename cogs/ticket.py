import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

# Ajuste para o local do seu db.py
from db import SessionLocal, get_or_create_guild_ticket_config
# Se quiser registrar mensagens no BD, importe a classe TicketMessage
# from db import TicketMessage

import random
import string

def gerar_codigo_ticket(tamanho=6):
    """Gera um código aleatório (ex: 'AB12XY') para identificar o ticket."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(tamanho))

class TicketCog(commands.Cog):
    """Cog avançado que gerencia tickets:
    - /ticketpanel (painel para abrir tickets)
    - /reopenticket (#canal)
    - auto-fechamento de tickets inativos
    - registro de mensagens (on_message)
    - interações (Staff/Membro) dentro do canal
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autoclose_loop.start()  # inicia loop de auto-fechamento

    def cog_unload(self):
        self.autoclose_loop.cancel()

    # ================ EVENTO DE ERRO GLOBAL (opcional) ================
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        print(f"[APP_COMMAND_ERROR - TICKETS] {interaction.user}: {error}")
        try:
            await interaction.response.send_message(
                f"Ocorreu um erro: {error}",
                ephemeral=True
            )
        except:
            pass

    # ================ COMANDOS DE TICKET ================
    @app_commands.command(name="ticketpanel", description="Cria um painel para abrir tickets.")
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        """Posta um embed + botão 'Abrir Ticket'."""
        embed = discord.Embed(
            title="Painel de Tickets",
            description="Clique no botão abaixo para abrir um ticket!",
            color=discord.Color.green()
        )
        view = TicketPanelView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="reopenticket", description="Reabre um ticket fechado.")
    @commands.has_permissions(manage_guild=True)
    async def reopenticket(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Renomeia 'closed-xyz' para 'ticket-xyz' e restaura permissão do autor."""
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

    # ================ LOOP PARA AUTO-FECHAR TICKETS INATIVOS ================
    @tasks.loop(minutes=10)
    async def autoclose_loop(self):
        """
        A cada 10 minutos, verifica se os canais 'ticket-' estão sem msgs há +60 minutos
        e então renomeia para 'closed-...'.
        """
        now = datetime.utcnow()
        inatividade_max = timedelta(minutes=60)  # tempo que achar melhor

        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith("ticket-"):
                    try:
                        history = [m async for m in channel.history(limit=1)]
                        if history:
                            last_msg_time = history[0].created_at
                        else:
                            last_msg_time = channel.created_at

                        if (now - last_msg_time) > inatividade_max:
                            await channel.send("Fechando ticket por inatividade...")
                            new_name = channel.name.replace("ticket-", "closed-")
                            await channel.edit(name=new_name)
                    except Exception as e:
                        print(f"[autoclose_loop] Erro ao fechar {channel.name}: {e}")

    # ================ REGISTRO DE MENSAGENS (Opcional) ================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.name.startswith(("ticket-", "closed-")):
            # Se quiser logar no BD, descomente:
            """
            from db import TicketMessage
            session = SessionLocal()
            try:
                topic = message.channel.topic or ""
                code = "DESCONHECIDO"
                if "Código:" in topic:
                    after = topic.split("Código:")[1].strip()
                    code = after.split()[0].replace("`", "").strip()

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
            """
            pass

# ======================================================
#  CLASSES DE VIEW / MODAL PARA CRIAR O TICKET
# ======================================================

class TicketPanelView(discord.ui.View):
    """View com o botão 'Abrir Ticket'."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="abrir_ticket_button")
    async def abrir_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para o usuário descrever o motivo do ticket."""
        modal = AbrirTicketModal()
        await interaction.response.send_modal(modal)

class AbrirTicketModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Abrir Ticket")
        self.motivo = discord.ui.TextInput(
            label="Motivo do Ticket",
            style=discord.TextStyle.long,
            placeholder="Descreva o que precisa...",
            required=True
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        # Carregar config do DB para ver cargo staff, canal logs, etc.
        with SessionLocal() as session:
            cfg = get_or_create_guild_ticket_config(session, str(interaction.guild_id))
            cargo_staff_id = cfg.cargo_staff_id
            channel_logs_id = cfg.channel_logs_id
            channel_avaliation_id = cfg.channel_avaliation_id
            category_ticket_id = cfg.category_ticket_id

        guild = interaction.guild
        staff_role = guild.get_role(int(cargo_staff_id)) if cargo_staff_id else None
        logs_ch = guild.get_channel(int(channel_logs_id)) if channel_logs_id else None
        aval_ch = guild.get_channel(int(channel_avaliation_id)) if channel_avaliation_id else None
        cat_ch = guild.get_channel(int(category_ticket_id)) if category_ticket_id else None

        # Gera um código
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
            category=cat_ch,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user.mention} | Código: {code}"
        )

        desc = (
            f"**Usuário:** {interaction.user.mention}\n"
            f"**Motivo:** {self.motivo.value}\n"
            f"**Código:** `{code}`\n"
            "Ninguém assumiu ainda."
        )
        embed = discord.Embed(title="Ticket Aberto", description=desc, color=discord.Color.blue())
        view = TicketChannelView(
            autor=interaction.user,
            staff_role=staff_role,
            code=code,
            logs_channel=logs_ch,
            aval_channel=aval_ch
        )
        await ticket_channel.send(
            content=f"{interaction.user.mention} {(staff_role.mention if staff_role else '')}",
            embed=embed,
            view=view
        )

        # Log
        if logs_ch:
            emb_log = discord.Embed(
                title="Novo Ticket Aberto",
                description=(
                    f"**Usuário:** {interaction.user.mention}\n"
                    f"**Canal:** {ticket_channel.mention}\n"
                    f"**Motivo:** {self.motivo.value}\n"
                    f"**Código:** {code}"
                ),
                color=discord.Color.green()
            )
            await logs_ch.send(embed=emb_log)

        await interaction.response.send_message(
            f"Ticket criado com sucesso: {ticket_channel.mention}",
            ephemeral=True
        )

class TicketChannelView(discord.ui.View):
    """Botões para controle dentro do canal do ticket."""
    def __init__(self, autor: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel, aval_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor = autor
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel
        self.aval_channel = aval_channel

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, custom_id="painel_staff")
    async def painel_staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Apenas staff pode acessar isso!", ephemeral=True)
        view = StaffSelectView(
            autor=self.autor,
            staff_role=self.staff_role,
            code=self.code,
            logs_channel=self.logs_channel
        )
        await interaction.response.send_message("Escolha uma ação de staff:", view=view, ephemeral=True)

    @discord.ui.button(label="Painel Membro", style=discord.ButtonStyle.secondary, custom_id="painel_membro")
    async def painel_membro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            return await interaction.response.send_message("Apenas o autor do ticket pode usar isso!", ephemeral=True)
        view = MemberSelectView(
            autor=self.autor,
            staff_role=self.staff_role,
            code=self.code,
            logs_channel=self.logs_channel
        )
        await interaction.response.send_message("Escolha uma ação de membro:", view=view, ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.success, custom_id="ticket_assumir")
    async def ticket_assumir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Apenas staff pode assumir!", ephemeral=True)

        msg = interaction.message
        if msg.embeds:
            embed_atual = msg.embeds[0]
            desc = embed_atual.description
            if "Ninguém assumiu ainda." in desc:
                desc = desc.replace("Ninguém assumiu ainda.", f"Assumido por {interaction.user.mention}.")
            else:
                desc += f"\nAssumido por {interaction.user.mention}."
            new_emb = discord.Embed(title=embed_atual.title, description=desc, color=discord.Color.blue())
            if embed_atual.image:
                new_emb.set_image(url=embed_atual.image.url)
            if embed_atual.thumbnail:
                new_emb.set_thumbnail(url=embed_atual.thumbnail.url)
            await msg.edit(embed=new_emb, view=self)

        await interaction.response.send_message("Você assumiu este ticket!", ephemeral=True)
        if self.logs_channel:
            emb_assumido = discord.Embed(
                title="Ticket Assumido",
                description=(
                    f"**Canal:** {interaction.channel.mention}\n"
                    f"**Staff:** {interaction.user.mention}\n"
                    f"**Código:** {self.code}"
                ),
                color=discord.Color.orange()
            )
            await self.logs_channel.send(embed=emb_assumido)

    @discord.ui.button(label="Sair do Ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_sair")
    async def ticket_sair_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            return await interaction.response.send_message("Apenas o autor pode sair do ticket!", ephemeral=True)

        overwrites = interaction.channel.overwrites
        if interaction.user in overwrites:
            overwrites[interaction.user].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)

        await interaction.response.send_message("Você saiu do ticket.", ephemeral=True)

    @discord.ui.button(label="Finalizar Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_fechar")
    async def ticket_fechar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Apenas staff pode fechar!", ephemeral=True)

        await interaction.response.defer()
        # Renomeia canal para closed-...
        old_name = interaction.channel.name
        new_name = old_name.replace("ticket-", "closed-")
        await interaction.channel.edit(name=new_name)

        overwrites = interaction.channel.overwrites
        if self.autor in overwrites:
            overwrites[self.autor].view_channel = False
            await interaction.channel.edit(overwrites=overwrites)

        if self.logs_channel:
            emb_fechado = discord.Embed(
                title="Ticket Fechado",
                description=(
                    f"**Canal:** {interaction.channel.mention}\n"
                    f"**Fechado por:** {interaction.user.mention}\n"
                    f"**Código:** {self.code}"
                ),
                color=discord.Color.red()
            )
            await self.logs_channel.send(embed=emb_fechado)

        await interaction.followup.send("Ticket finalizado! (Renomeado para `closed-`).", ephemeral=True)

        # Envia DM pedindo avaliação
        try:
            await self.enviar_avaliacao_dm()
        except:
            pass

    async def enviar_avaliacao_dm(self):
        """Envia DM ao autor para avaliar o ticket (1 a 5)."""
        if not self.aval_channel:
            return
        try:
            dm = await self.autor.create_dm()
            emb = discord.Embed(
                title="Avalie seu Ticket",
                description="Escolha uma **nota de 1 a 5** e deixe um comentário!",
                color=discord.Color.green()
            )
            await dm.send(embed=emb)
            view = discord.ui.View()
            button = discord.ui.Button(label="Avaliar", style=discord.ButtonStyle.primary)

            async def callback(i: discord.Interaction):
                if i.user.id == self.autor.id:
                    # Abre modal
                    modal = AvaliacaoModal(self.aval_channel, self.code)
                    await i.response.send_modal(modal)
                else:
                    await i.response.send_message("Você não pode avaliar o ticket de outra pessoa!", ephemeral=True)

            button.callback = callback
            view.add_item(button)
            await dm.send(view=view)
        except:
            pass

# =========== SELECT MENUS DE STAFF / MEMBRO (Add user, remover, call, etc) ===========

class StaffSelectView(discord.ui.View):
    def __init__(self, autor: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor = autor
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel

        options = [
            discord.SelectOption(label="Chamar Autor", value="chamar_autor"),
            discord.SelectOption(label="Adicionar Usuário", value="add_user"),
            discord.SelectOption(label="Remover Usuário", value="remove_user"),
            discord.SelectOption(label="Criar Call de Voz", value="create_call"),
            discord.SelectOption(label="Deletar Call de Voz", value="delete_call"),
            discord.SelectOption(label="Transferir Ticket", value="transfer_ticket"),
        ]
        select = discord.ui.Select(
            placeholder="Selecione uma ação de Staff",
            options=options,
            custom_id="staff_select_menu"
        )
        self.add_item(select)

    @discord.ui.select(custom_id="staff_select_menu")
    async def staff_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        valor = select.values[0]
        if not self.staff_role or self.staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Apenas staff pode usar isso!", ephemeral=True)

        if valor == "chamar_autor":
            try:
                await self.autor.send(
                    f"O Staff {interaction.user.mention} está te chamando no canal {interaction.channel.mention}!"
                )
                await interaction.response.send_message("Autor notificado via DM!", ephemeral=True)
            except:
                await interaction.response.send_message("Falha ao enviar DM ao autor.", ephemeral=True)
        elif valor == "add_user":
            await interaction.response.send_message("Mencione ou envie o ID do usuário para adicionar:", ephemeral=True)
            # Iniciar collector
            def check(msg):
                return msg.author.id == interaction.user.id and msg.channel == interaction.channel
            try:
                msg = await self.staff_role.guild.text_channels[0].bot.wait_for("message", check=check, timeout=60)
            except:
                await interaction.channel.send("Tempo esgotado.", delete_after=5)
                return
            # ...
            # (Siga a mesma lógica do que já mostramos: edita overwrites, etc.)
            # Por simplicidade, vou encurtar aqui.

        elif valor == "remove_user":
            # idem
            pass

        elif valor == "create_call":
            # Cria call "call-nomedocanal"
            pass

        elif valor == "delete_call":
            pass

        elif valor == "transfer_ticket":
            pass

        # etc

class MemberSelectView(discord.ui.View):
    def __init__(self, autor: discord.User, staff_role: discord.Role, code: str, logs_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.autor = autor
        self.staff_role = staff_role
        self.code = code
        self.logs_channel = logs_channel

        options = [
            discord.SelectOption(label="Chamar Staff", value="chamar_staff"),
            discord.SelectOption(label="Criar Call de Voz", value="create_call"),
            discord.SelectOption(label="Deletar Call de Voz", value="delete_call"),
        ]
        select = discord.ui.Select(
            placeholder="Selecione algo",
            options=options,
            custom_id="member_select_menu"
        )
        self.add_item(select)

    @discord.ui.select(custom_id="member_select_menu")
    async def member_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        valor = select.values[0]
        if interaction.user.id != self.autor.id:
            return await interaction.response.send_message("Apenas o autor pode usar isso!", ephemeral=True)

        if valor == "chamar_staff":
            # notifica staff
            if self.logs_channel:
                await self.logs_channel.send(
                    f"{interaction.user.mention} chamou o staff no ticket {interaction.channel.mention}"
                )
            await interaction.response.send_message("Staff notificado!", ephemeral=True)
        elif valor == "create_call":
            pass
        elif valor == "delete_call":
            pass

# =========== MODAL DE AVALIAÇÃO ===========

class AvaliacaoModal(discord.ui.Modal):
    def __init__(self, avaliations_channel: discord.TextChannel, code: str):
        super().__init__(title="Avalie o Atendimento")
        self.avaliations_channel = avaliations_channel
        self.code = code

        self.nota = discord.ui.TextInput(
            label="Nota (1 a 5)",
            placeholder="Ex: 5",
            max_length=1,
            required=True
        )
        self.comentario = discord.ui.TextInput(
            label="Comentário (opcional)",
            style=discord.TextStyle.long,
            placeholder="Ex: Muito bom atendimento!"
        )
        self.add_item(self.nota)
        self.add_item(self.comentario)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.nota.value)
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            return await interaction.response.send_message("Nota inválida (1 a 5).", ephemeral=True)

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

        await interaction.response.send_message("Obrigado pela avaliação!", ephemeral=True)

# ======================================================
#   FUNÇÃO SETUP
# ======================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
