import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class TempChannelsView(discord.ui.View):
    """
    Esta View contém os botões para gerenciar canais temporários.
    Persistirá enquanto o bot estiver rodando.
    """
    def __init__(self, cog):
        super().__init__(timeout=None)  # timeout=None => persiste até reiniciar ou manual
        self.cog = cog  # referência ao cog principal, para acessar métodos/dicionários

    @discord.ui.button(label="Criar Canal", style=discord.ButtonStyle.green, custom_id="tempchannel_create")
    async def create_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Quando o usuário clica em "Criar Canal", abrimos um Modal
        para ele digitar o nome do canal.
        """
        if not interaction.guild:
            return await interaction.response.send_message(
                "Não funciona em DMs.",
                ephemeral=True
            )

        # Exibimos um Modal para o usuário escrever o nome do canal
        modal = CreateChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Renomear Canal", style=discord.ButtonStyle.blurple, custom_id="tempchannel_rename")
    async def rename_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Abre um Modal para o usuário digitar o novo nome do canal temporário.
        Só funciona se o usuário for dono de algum canal temporário.
        """
        # Precisamos verificar se o user está em um canal de voz
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você precisa estar em seu canal temporário para renomeá-lo.",
                ephemeral=True
            )

        channel_id = interaction.user.voice.channel.id
        # Verifica se este canal está na nossa lista
        if channel_id not in self.cog.channel_owners:
            return await interaction.response.send_message(
                "Este canal não é temporário ou não foi criado por mim.",
                ephemeral=True
            )

        owner_id = self.cog.channel_owners[channel_id]
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(
                "Você não é o dono deste canal temporário!",
                ephemeral=True
            )

        # Se tudo certo, abrimos o modal de renomear
        modal = RenameChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Definir Limite", style=discord.ButtonStyle.gray, custom_id="tempchannel_limit")
    async def set_limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Abre um Modal para definir o limite de usuários do canal de voz.
        """
        # Mesma checagem (precisa estar em canal temporário e ser dono)
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você precisa estar em seu canal temporário para definir limite.",
                ephemeral=True
            )

        channel_id = interaction.user.voice.channel.id
        if channel_id not in self.cog.channel_owners:
            return await interaction.response.send_message(
                "Este canal não é temporário ou não foi criado por mim.",
                ephemeral=True
            )

        owner_id = self.cog.channel_owners[channel_id]
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(
                "Você não é o dono deste canal temporário!",
                ephemeral=True
            )

        modal = LimitChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Fechar Canal", style=discord.ButtonStyle.red, custom_id="tempchannel_close")
    async def close_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Fecha (deleta) o canal temporário, se o usuário for dono.
        """
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você precisa estar no seu canal temporário para fechá-lo.",
                ephemeral=True
            )

        channel = interaction.user.voice.channel
        if channel.id not in self.cog.channel_owners:
            return await interaction.response.send_message(
                "Este canal não é temporário ou não foi criado por mim.",
                ephemeral=True
            )

        owner_id = self.cog.channel_owners[channel.id]
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(
                "Você não é o dono deste canal temporário!",
                ephemeral=True
            )

        # Deleta
        await channel.delete(reason="Fechado pelo dono do canal.")
        # Remove do dict
        self.cog.channel_owners.pop(channel.id, None)
        # Cancela timer se houver
        if channel.id in self.cog.delete_timers:
            self.cog.delete_timers[channel.id].cancel()
            self.cog.delete_timers.pop(channel.id, None)

        await interaction.response.send_message(
            "Canal temporário fechado com sucesso!",
            ephemeral=True
        )


# ============================================================
#            MODALS PARA CRIAR/RENOMEAR/DEFINIR LIMITE
# ============================================================

class CreateChannelModal(discord.ui.Modal, title="Criar Canal de Voz"):
    channel_name = discord.ui.TextInput(
        label="Nome do Canal",
        style=discord.TextStyle.short,
        placeholder="Ex: Sala do Fulano",
        required=True,
        max_length=50
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "Erro: Guild não encontrada.",
                ephemeral=True
            )

        nome = self.channel_name.value
        # Cria o canal de voz (opcional: crie uma categoria 'Canais Temporários')
        try:
            voice_channel = await guild.create_voice_channel(
                name=nome,
                reason=f"Criado por {interaction.user} via TempChannels"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para criar canais.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"Erro ao criar canal: {e}",
                ephemeral=True
            )

        # Armazena no dict
        self.cog.channel_owners[voice_channel.id] = interaction.user.id

        await interaction.response.send_message(
            f"Canal de voz **{nome}** criado!\n"
            "Entre nele para usar. Ele será removido ao ficar vazio."
        )

class RenameChannelModal(discord.ui.Modal, title="Renomear Canal"):
    new_name = discord.ui.TextInput(
        label="Novo Nome",
        style=discord.TextStyle.short,
        placeholder="Ex: Sala do Fulano 2.0",
        required=True,
        max_length=50
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você não está em um canal de voz.",
                ephemeral=True
            )

        channel = interaction.user.voice.channel
        # Renomeia
        try:
            await channel.edit(name=self.new_name.value)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para renomear este canal.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"Erro ao renomear: {e}",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Canal renomeado para **{self.new_name.value}** com sucesso!"
        )

class LimitChannelModal(discord.ui.Modal, title="Definir Limite de Usuários"):
    limit = discord.ui.TextInput(
        label="Limite de Usuários (0 para ilimitado)",
        style=discord.TextStyle.short,
        placeholder="Ex: 5",
        required=True,
        max_length=2
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você não está em um canal de voz.",
                ephemeral=True
            )

        channel = interaction.user.voice.channel
        try:
            value = int(self.limit.value)
        except ValueError:
            return await interaction.response.send_message(
                "Por favor, insira um número inteiro válido.",
                ephemeral=True
            )

        # Define user_limit
        if value < 0:
            value = 0

        try:
            await channel.edit(user_limit=value)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para alterar este canal.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"Erro ao definir limite: {e}",
                ephemeral=True
            )

        if value == 0:
            await interaction.response.send_message(
                "Limite removido (ilimitado)."
            )
        else:
            await interaction.response.send_message(
                f"Limite de usuários definido para **{value}**."
            )

# ============================================================
#                  O COG PRINCIPAL
# ============================================================

class TempChannelsButtonsCog(commands.Cog):
    """
    Cog que gera um embed com botões para criar/renomear/limitar/fechar
    canais de voz temporários.
    Também lida com a exclusão dos canais quando ficam vazios.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id -> user_id (dono)
        self.channel_owners = {}
        # channel_id -> asyncio.Task (timer de deleção)
        self.delete_timers = {}

    @app_commands.command(
        name="tempchannelpanel",
        description="Envia um painel de controle para canais temporários."
    )
    async def tempchannelpanel(self, interaction: discord.Interaction):
        """
        Envia um embed permanente com botões (create, rename, set limit, close).
        """
        embed = discord.Embed(
            title="Gerenciador de Canais Temporários",
            description=(
                "**Crie, renomeie ou feche** um canal de voz temporário usando os botões.\n\n"
                "➡ **Criar Canal**: Abre um modal para digitar o nome.\n"
                "➡ **Renomear Canal**: Se você for dono e estiver no canal.\n"
                "➡ **Definir Limite**: Ajusta o limite de usuários.\n"
                "➡ **Fechar Canal**: Deleta o canal se você for dono.\n\n"
                "Canais vazios serão removidos após 30 segundos."
            ),
            color=discord.Color.blue()
        )
        view = TempChannelsView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Se o user saiu de um canal temporário, pode estar vazio
        if before.channel and before.channel.id in self.channel_owners:
            channel = before.channel
            if len(channel.members) == 0:
                # Agendar deleção
                await self.schedule_deletion(channel)

        # Se o user entrou num canal temporário e havia um timer de deleção, cancela
        if after.channel and after.channel.id in self.channel_owners:
            channel_id = after.channel.id
            if channel_id in self.delete_timers:
                task = self.delete_timers.pop(channel_id)
                task.cancel()

    async def schedule_deletion(self, channel: discord.VoiceChannel, delay=30):
        """
        Agenda a deleção do canal em 'delay' segundos se continuar vazio.
        """
        # Se já há um timer, cancela
        if channel.id in self.delete_timers:
            self.delete_timers[channel.id].cancel()

        async def deletion_coroutine():
            await asyncio.sleep(delay)
            if channel.id in self.channel_owners:
                # Verifica se ainda está vazio
                if len(channel.members) == 0:
                    try:
                        await channel.delete(reason="Canal temporário vazio.")
                    except:
                        pass
                    self.channel_owners.pop(channel.id, None)
                    self.delete_timers.pop(channel.id, None)

        task = asyncio.create_task(deletion_coroutine())
        self.delete_timers[channel.id] = task

    # Ao descarregar o cog, cancela timers
    async def cog_unload(self):
        for task in self.delete_timers.values():
            task.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(TempChannelsButtonsCog(bot))
