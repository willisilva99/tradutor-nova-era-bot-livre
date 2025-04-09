import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# --------------------------------------------------------
#  Helper para enviar embed e apagar em 30s
# --------------------------------------------------------
async def send_temporary_embed(
    interaction: discord.Interaction,
    embed: discord.Embed,
    delay: int = 30
) -> None:
    """
    Envia um embed (visível a todos) e deleta após 'delay' segundos.
    """
    await interaction.response.send_message(embed=embed, ephemeral=False)
    # Pega a mensagem que acabamos de enviar
    msg = await interaction.original_response()
    await asyncio.sleep(delay)
    # Tenta apagar
    try:
        await msg.delete()
    except:
        pass

# =========================
# Modals
# =========================
class CreateChannelModal(discord.ui.Modal, title="Criar Canal de Voz"):
    channel_name = discord.ui.TextInput(
        label="📝 Nome do Canal",
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
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Erro",
                    description="Guild não encontrada.",
                    color=discord.Color.red()
                )
            )

        nome = self.channel_name.value

        # Se quiser criar na mesma categoria do painel:
        category = interaction.channel.category  # ou None para fora de categoria

        try:
            voice_channel = await guild.create_voice_channel(
                name=nome,
                category=category,
                reason=f"Criado por {interaction.user} via TempChannels"
            )
        except discord.Forbidden:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Permissão Insuficiente",
                    description="Não tenho permissão para criar canais.",
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Erro ao criar canal",
                    description=str(e),
                    color=discord.Color.red()
                )
            )

        self.cog.channel_owners[voice_channel.id] = interaction.user.id

        embed = discord.Embed(
            title="✅ Canal Criado",
            description=(
                f"**Canal de voz** `{nome}` criado com sucesso!\n"
                "Entre nele para usar. Ele será removido ao ficar vazio por 30s."
            ),
            color=discord.Color.green()
        )
        await send_temporary_embed(interaction, embed)


class RenameChannelModal(discord.ui.Modal, title="Renomear Canal"):
    new_name = discord.ui.TextInput(
        label="📝 Novo Nome",
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
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Inválida",
                    description="Você não está em um canal de voz.",
                    color=discord.Color.red()
                )
            )

        channel = interaction.user.voice.channel
        try:
            await channel.edit(name=self.new_name.value)
        except discord.Forbidden:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Sem Permissão",
                    description="Não tenho permissão para renomear este canal.",
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Erro ao renomear",
                    description=str(e),
                    color=discord.Color.red()
                )
            )

        embed = discord.Embed(
            title="📝 Canal Renomeado",
            description=f"O canal agora se chama **{self.new_name.value}**!",
            color=discord.Color.blue()
        )
        await send_temporary_embed(interaction, embed)


class LimitChannelModal(discord.ui.Modal, title="Definir Limite de Usuários"):
    limit = discord.ui.TextInput(
        label="🔢 Limite de Usuários (0 para ilimitado)",
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
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Inválida",
                    description="Você não está em um canal de voz.",
                    color=discord.Color.red()
                )
            )

        channel = interaction.user.voice.channel
        try:
            value = int(self.limit.value)
        except ValueError:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Valor Inválido",
                    description="Insira um número inteiro, ex: 5 ou 0.",
                    color=discord.Color.red()
                )
            )

        if value < 0:
            value = 0

        try:
            await channel.edit(user_limit=value)
        except discord.Forbidden:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Sem Permissão",
                    description="Não tenho permissão para alterar este canal.",
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Erro ao definir limite",
                    description=str(e),
                    color=discord.Color.red()
                )
            )

        if value == 0:
            emb_text = "Limite removido (ilimitado)."
        else:
            emb_text = f"Limite de usuários definido para **{value}**."

        embed = discord.Embed(
            title="🔢 Limite Definido",
            description=emb_text,
            color=discord.Color.blue()
        )
        await send_temporary_embed(interaction, embed)


# --------------------------------------------------------
# VIEW DE BOTÕES
# --------------------------------------------------------
class TempChannelsView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Criar Canal", style=discord.ButtonStyle.green, emoji="🆕", custom_id="tempchannel_create")
    async def create_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Erro",
                    description="Não funciona em DMs.",
                    color=discord.Color.red()
                )
            )
        modal = CreateChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Renomear Canal", style=discord.ButtonStyle.blurple, emoji="📝", custom_id="tempchannel_rename")
    async def rename_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se o user está em canal e se é dono
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Inválida",
                    description="Você precisa estar em seu canal temporário para renomeá-lo.",
                    color=discord.Color.red()
                )
            )
        channel_id = interaction.user.voice.channel.id
        if channel_id not in self.cog.channel_owners:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Não é um canal temporário",
                    description="Este canal não foi criado por mim.",
                    color=discord.Color.red()
                )
            )
        owner_id = self.cog.channel_owners[channel_id]
        if owner_id != interaction.user.id:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Negada",
                    description="Você não é o dono deste canal!",
                    color=discord.Color.red()
                )
            )

        modal = RenameChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Definir Limite", style=discord.ButtonStyle.gray, emoji="🔢", custom_id="tempchannel_limit")
    async def set_limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Inválida",
                    description="Você precisa estar em seu canal temporário para definir limite.",
                    color=discord.Color.red()
                )
            )
        channel_id = interaction.user.voice.channel.id
        if channel_id not in self.cog.channel_owners:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Não é um canal temporário",
                    description="Este canal não foi criado por mim.",
                    color=discord.Color.red()
                )
            )
        owner_id = self.cog.channel_owners[channel_id]
        if owner_id != interaction.user.id:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Negada",
                    description="Você não é o dono deste canal!",
                    color=discord.Color.red()
                )
            )

        modal = LimitChannelModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Fechar Canal", style=discord.ButtonStyle.red, emoji="🔒", custom_id="tempchannel_close")
    async def close_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Inválida",
                    description="Você precisa estar no seu canal temporário para fechá-lo.",
                    color=discord.Color.red()
                )
            )

        channel = interaction.user.voice.channel
        if channel.id not in self.cog.channel_owners:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Não é um canal temporário",
                    description="Este canal não foi criado por mim.",
                    color=discord.Color.red()
                )
            )
        owner_id = self.cog.channel_owners[channel.id]
        if owner_id != interaction.user.id:
            return await send_temporary_embed(
                interaction,
                discord.Embed(
                    title="❌ Ação Negada",
                    description="Você não é o dono deste canal!",
                    color=discord.Color.red()
                )
            )

        await channel.delete(reason="Fechado pelo dono do canal.")
        self.cog.channel_owners.pop(channel.id, None)
        if channel.id in self.cog.delete_timers:
            self.cog.delete_timers[channel.id].cancel()
            self.cog.delete_timers.pop(channel.id, None)

        embed = discord.Embed(
            title="🔒 Canal Fechado",
            description="Canal temporário fechado com sucesso!",
            color=discord.Color.red()
        )
        await send_temporary_embed(interaction, embed)


# --------------------------------------------------------
#  COG PRINCIPAL
# --------------------------------------------------------
class TempChannelsButtonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id -> user_id (dono)
        self.channel_owners = {}
        # channel_id -> asyncio.Task (timer de deleção)
        self.delete_timers = {}

    @app_commands.command(
        name="tempchannelpanel",
        description="Exibe um painel de botões para criar/gerenciar canais temporários"
    )
    async def tempchannelpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎉 Gerenciador de Canais Temporários",
            description=(
                "Use os **botões abaixo** para criar, renomear, definir limite ou fechar seu canal de voz.\n\n"
                "**Canais vazios** serão **removidos** após 30s.\n\n"
                "◾ **Criar Canal**: Cria um canal de voz provisório.\n"
                "◾ **Renomear Canal**: Muda o nome do seu canal.\n"
                "◾ **Definir Limite**: Ajusta quantas pessoas podem entrar.\n"
                "◾ **Fechar Canal**: Deleta o canal imediatamente.\n"
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
        """
        Aguarda 'delay' segundos e deleta o canal se continuar vazio.
        """
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
