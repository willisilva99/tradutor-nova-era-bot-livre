import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import functools

# Se preferir usar yt-dlp:
# import yt_dlp as youtube_dl
import youtube_dl

# ==================================================
#   CONFIGURAÇÃO DO youtube_dl ou yt-dlp
# ==================================================
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "ignoreerrors": True,
    "no_warnings": True,
    "default_search": "auto",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
}
FFMPEG_OPTIONS = {
    "options": "-vn"  # sem vídeo
}

# ==================================================
#   Helper para enviar mensagem e apagar em 30s
# ==================================================
async def send_message_and_delete_later(
    interaction: discord.Interaction,
    content: str = None,
    embed: discord.Embed = None,
    view: discord.ui.View = None,
    delay: int = 30
):
    """
    Envia uma mensagem pública (ephemeral=False) e apaga após 'delay' segundos.
    - Se a interaction ainda não foi respondida, usamos interaction.response.send_message.
    - Se já foi respondida, usamos interaction.followup.send.
    Retorna o objeto da mensagem enviada.
    """
    if not interaction.response.is_done():
        # Ainda não respondemos ao Interaction
        sent_msg = await interaction.response.send_message(
            content=content,
            embed=embed,
            view=view,
            ephemeral=False
        )
        # O retorno de send_message() via InteractionResponse não é a mensagem, então pegamos:
        msg = await interaction.original_response()
    else:
        # Já respondemos antes; usar followup
        msg = await interaction.followup.send(
            content=content,
            embed=embed,
            view=view
        )

    # Apagar depois de X segundos
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass
    return msg

# --------------------------------------------------
#   Classe Track - guarda info da música
# --------------------------------------------------
class Track:
    def __init__(self, source, title, url):
        self.source = source  # FFmpegPCMAudio
        self.title = title
        self.url = url

# ======================================================================
#  MODAL para "Play" - pergunta a URL ou nome da música
# ======================================================================
class PlaySongModal(discord.ui.Modal, title="Tocar Música"):
    query = discord.ui.TextInput(
        label="Nome / URL da música",
        style=discord.TextStyle.short,
        placeholder="Ex: https://youtube.com/...",
        required=True
    )

    def __init__(self, cog, interaction: discord.Interaction):
        super().__init__()
        self.cog = cog
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        # Ao submeter o modal, chamamos play_music no Cog
        await self.cog.play_music(interaction, self.query.value)

# ======================================================================
#  VIEW (Botões) - controla a música
# ======================================================================
class MusicView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)  # sem timeout
        self.cog = cog

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, emoji="🔊")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.join_voice(interaction)

    @discord.ui.button(label="Play", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PlaySongModal(self.cog, interaction)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.gray, emoji="⏯️")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.pause_resume(interaction)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.gray, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.skip_track(interaction)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.stop_music(interaction)

    @discord.ui.button(label="Fila", style=discord.ButtonStyle.secondary, emoji="🎶")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_queue(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.leave_voice(interaction)

# ======================================================================
#   COG PRINCIPAL DE MÚSICA
# ======================================================================
class MusicButtonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Fila de reprodução: guild_id -> lista de Track
        self.queues = {}

    # ------------------------------------------------------------------
    #   /musicpanel - manda o embed com botões (some em 30s)
    # ------------------------------------------------------------------
    @app_commands.command(name="musicpanel", description="Exibe um painel de botões para controlar a música.")
    async def musicpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎶 Painel de Música",
            description=(
                "Use os **botões** abaixo para:\n"
                "• **Entrar** no seu canal\n"
                "• **Play** (abrir modal para URL / nome)\n"
                "• **Pause/Resume**\n"
                "• **Skip**\n"
                "• **Stop** (parar e limpar fila)\n"
                "• **Fila** (ver o que está na fila)\n"
                "• **Sair** do canal\n\n"
                "Este painel será apagado em 30s."
            ),
            color=discord.Color.blurple()
        )
        view = MusicView(self)
        # Manda a mensagem com embed+view e apaga depois de 30s
        await send_message_and_delete_later(interaction, embed=embed, view=view, delay=30)

    # ------------------------------------------------------------------
    #           FUNÇÕES CHAMADAS PELOS BOTÕES / MODAL
    # ------------------------------------------------------------------
    async def join_voice(self, interaction: discord.Interaction):
        user = interaction.user
        if not user.voice or not user.voice.channel:
            await send_message_and_delete_later(
                interaction,
                content="Você precisa estar em um canal de voz!"
            )
            return

        channel = user.voice.channel
        voice_client = interaction.guild.voice_client

        # Tentar conectar ou mover
        try:
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(channel)
            else:
                await channel.connect()
        except discord.Forbidden:
            await send_message_and_delete_later(
                interaction,
                content="❌ Não tenho permissão para entrar/mover para este canal de voz!"
            )
            return
        except Exception as e:
            await send_message_and_delete_later(
                interaction,
                content=f"❌ Erro ao conectar ao canal de voz: {e}"
            )
            return

        await send_message_and_delete_later(
            interaction,
            content=f"Entrei no canal de voz: **{channel}**"
        )

    async def play_music(self, interaction: discord.Interaction, search: str):
        guild = interaction.guild
        voice_client = guild.voice_client

        # Se o bot não está no canal, tente conectar
        if not voice_client or not voice_client.is_connected():
            if not interaction.user.voice or not interaction.user.voice.channel:
                await send_message_and_delete_later(
                    interaction,
                    content="Você não está em um canal de voz!"
                )
                return
            try:
                await interaction.user.voice.channel.connect()
            except discord.Forbidden:
                await send_message_and_delete_later(
                    interaction,
                    content="❌ Não tenho permissão para entrar no canal de voz!"
                )
                return
            except Exception as e:
                await send_message_and_delete_later(
                    interaction,
                    content=f"❌ Erro ao conectar ao canal de voz: {e}"
                )
                return
            voice_client = guild.voice_client

        # Aviso "Buscando..."
        await send_message_and_delete_later(interaction, content="Buscando...")

        # Tenta obter a música
        track = await self.get_track(search)
        if not track:
            await send_message_and_delete_later(
                interaction,
                content="❌ Não foi possível obter esta música."
            )
            return

        # Adicionar na fila
        queue = self.queues.setdefault(guild.id, [])
        queue.append(track)

        if not voice_client.is_playing():
            # Se não está tocando nada, toca
            await self.play_next(guild)
            await send_message_and_delete_later(
                interaction,
                content=f"🎶 Tocando agora: **{track.title}**"
            )
        else:
            await send_message_and_delete_later(
                interaction,
                content=f"Adicionado à fila: **{track.title}**"
            )

    async def pause_resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await send_message_and_delete_later(
                interaction,
                content="O bot não está no canal de voz."
            )
            return

        if voice_client.is_paused():
            voice_client.resume()
            await send_message_and_delete_later(interaction, content="▶️ Música retomada.")
        elif voice_client.is_playing():
            voice_client.pause()
            await send_message_and_delete_later(interaction, content="⏸️ Música pausada.")
        else:
            await send_message_and_delete_later(
                interaction,
                content="Não há música tocando/pausada no momento."
            )

    async def skip_track(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await send_message_and_delete_later(
                interaction,
                content="Não há música tocando para pular."
            )
            return
        voice_client.stop()
        await send_message_and_delete_later(interaction, content="⏭️ Música pulada!")

    async def stop_music(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            self.queues[interaction.guild.id] = []
            await send_message_and_delete_later(
                interaction,
                content="🛑 Parei a música e limpei a fila!"
            )
        else:
            await send_message_and_delete_later(
                interaction,
                content="O bot não está tocando nada no momento."
            )

    async def show_queue(self, interaction: discord.Interaction):
        queue = self.queues.get(interaction.guild.id, [])
        if not queue:
            await send_message_and_delete_later(
                interaction,
                content="A fila está vazia."
            )
            return
        desc = "\n".join(f"**{i+1}.** {t.title}" for i, t in enumerate(queue))
        embed = discord.Embed(
            title="🎶 Fila de Reprodução",
            description=desc,
            color=discord.Color.blue()
        )
        await send_message_and_delete_later(interaction, embed=embed)

    async def leave_voice(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await send_message_and_delete_later(
                interaction,
                content="Não estou em nenhum canal de voz."
            )
            return
        await voice_client.disconnect()
        self.queues[interaction.guild.id] = []
        await send_message_and_delete_later(interaction, content="Saí do canal de voz!")

    # ------------------------------------------------------------------
    #   LÓGICA INTERNA PARA TOCAR A FILA
    # ------------------------------------------------------------------
    async def play_next(self, guild: discord.Guild):
        voice_client = guild.voice_client
        if not voice_client:
            return

        queue = self.queues.setdefault(guild.id, [])
        if len(queue) == 0:
            # Fila vazia => Se quiser, desconectar
            # await voice_client.disconnect()
            return

        track = queue.pop(0)

        def after_playing(err):
            if err:
                print(f"[ERRO AO TOCAR MÚSICA] {err}")
            coro = self.play_next(guild)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except:
                pass

        voice_client.play(track.source, after=after_playing)

    # ------------------------------------------------------------------
    #   BUSCAR MÚSICA (youtube_dl)
    # ------------------------------------------------------------------
    async def get_track(self, search: str) -> Track:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            functools.partial(self.ytdl_extract, search)
        )
        if not data:
            return None

        url = data["url"]
        title = data.get("title") or "Desconhecido"
        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        return Track(source, title, url)

    def ytdl_extract(self, search: str):
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(search, download=False)
            if not info:
                return None
            if "entries" in info:
                info = info["entries"][0]  # pega a primeira
                if not info:
                    return None
            return {
                "url": info["url"],
                "title": info.get("title"),
            }

# ============================================================
#   SETUP DO COG
# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicButtonsCog(bot))
