import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class TempChannelsView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Criar Canal", style=discord.ButtonStyle.green, custom_id="tempchannel_create")
    async def create_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Não funciona em DMs.", ephemeral=True)

        modal = CreateChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Renomear Canal", style=discord.ButtonStyle.blurple, custom_id="tempchannel_rename")
    async def rename_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Você precisa estar em seu canal temporário para renomeá-lo.",
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

        modal = RenameChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Definir Limite", style=discord.ButtonStyle.gray, custom_id="tempchannel_limit")
    async def set_limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        await channel.delete(reason="Fechado pelo dono do canal.")
        self.cog.channel_owners.pop(channel.id, None)
        if channel.id in self.cog.delete_timers:
            self.cog.delete_timers[channel.id].cancel()
            self.cog.delete_timers.pop(channel.id, None)

        await interaction.response.send_message("Canal temporário fechado com sucesso!", ephemeral=True)


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
            return await interaction.response.send_message("Erro: Guild não encontrada.", ephemeral=True)

        nome = self.channel_name.value

        # Pega a categoria do canal de texto onde o usuário clicou no botão
        # Se não tiver categoria, fica None
        category = interaction.channel.category

        try:
            # Cria canal de voz na mesma categoria do embed
            voice_channel = await guild.create_voice_channel(
                name=nome,
                category=category,
                reason=f"Criado por {interaction.user} via TempChannels"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para criar canais.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(f"Erro ao criar canal: {e}", ephemeral=True)

        self.cog.channel_owners[voice_channel.id] = interaction.user.id

        # Envia mensagem normal (não ephemeral)
        await interaction.response.send_message(
            f"Canal de voz **{nome}** criado!\n"
            "Entre nele para usar. Ele será removido ao ficar vazio."
        )

        # Depois de 30s, apaga essa mensagem:
        created_msg = await interaction.original_response()
        await asyncio.sleep(30)
        try:
            await created_msg.delete()
        except discord.HTTPException:
            pass


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
        try:
            await channel.edit(name=self.new_name.value)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para renomear este canal.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(f"Erro ao renomear: {e}", ephemeral=True)

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
            return await interaction.response.send_message(f"Erro ao definir limite: {e}", ephemeral=True)

        if value == 0:
            await interaction.response.send_message("Limite removido (ilimitado).")
        else:
            await interaction.response.send_message(f"Limite de usuários definido para **{value}**.")


class TempChannelsButtonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_owners = {}
        self.delete_timers = {}

    @app_commands.command(
        name="tempchannelpanel",
        description="Envia um painel de controle para canais temporários."
    )
    async def tempchannelpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Gerenciador de Canais Temporários",
            description=(
                "Use os botões abaixo para criar, renomear, definir limite ou fechar seu canal de voz.\n"
                "**Os canais são removidos** automaticamente ao ficarem vazios por 30s."
            ),
            color=discord.Color.blue()
        )
        view = TempChannelsView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Se saiu de um canal temporário, pode ficar vazio
        if before.channel and before.channel.id in self.channel_owners:
            channel = before.channel
            if len(channel.members) == 0:
                await self.schedule_deletion(channel)

        # Se entrou num canal temporário que estava marcado para deleção, cancela
        if after.channel and after.channel.id in self.channel_owners:
            channel_id = after.channel.id
            if channel_id in self.delete_timers:
                task = self.delete_timers.pop(channel_id)
                task.cancel()

    async def schedule_deletion(self, channel: discord.VoiceChannel, delay=30):
        if channel.id in self.delete_timers:
            self.delete_timers[channel.id].cancel()

        async def deletion_coroutine():
            await asyncio.sleep(delay)
            if channel.id in self.channel_owners:
                if len(channel.members) == 0:
                    try:
                        await channel.delete(reason="Canal temporário vazio.")
                    except:
                        pass
                    self.channel_owners.pop(channel.id, None)
                    self.delete_timers.pop(channel.id, None)

        task = asyncio.create_task(deletion_coroutine())
        self.delete_timers[channel.id] = task

    async def cog_unload(self):
        for task in self.delete_timers.values():
            task.cancel()

async def setup(bot: commands.Bot):
    await bot.add_cog(TempChannelsButtonsCog(bot))
