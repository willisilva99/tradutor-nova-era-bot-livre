import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import functools
import yt_dlp as youtube_dl  # Usando yt-dlp

# ==================================================
#   CONFIGURAÇÃO DO yt-dlp
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

# --------------------------------------------------
#   HELPER: Envia mensagem de resposta e apaga após 30 segundos
# --------------------------------------------------
async def send_temporary_message(
    interaction: discord.Interaction,
    content: str = None,
    embed: discord.Embed = None,
    view: discord.ui.View = None,
    delay: int = 30
):
    """
    Envia uma mensagem (usando response se ainda não respondido ou followup)
    e a deleta após 'delay' segundos.
    """
    if not interaction.response.is_done():
        await interaction.response.send_message(
            content=content,
            embed=embed,
            view=view,
            ephemeral=False
        )
        msg = await interaction.original_response()
    else:
        msg = await interaction.followup.send(
            content=content,
            embed=embed,
            view=view
        )
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass
    return msg

# --------------------------------------------------
#   Classe Track - Armazena informações da música
# --------------------------------------------------
class Track:
    def __init__(self, source, title, url):
        self.source = source  # discord.FFmpegPCMAudio
        self.title = title
        self.url = url

# ======================================================================
#   Modal para "Play" - Pergunta a URL ou nome da música
# ======================================================================
class PlaySongModal(discord.ui.Modal, title="▶️ Tocar Música"):
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
        await self.cog.play_music(interaction, self.query.value)

# ======================================================================
#   View com Botões para controle da música
# ======================================================================
class MusicView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
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
#   COG PRINCIPAL DE MÚSICA COM BOTÕES
# ======================================================================
class MusicButtonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Fila de reprodução por guild: guild_id -> lista de Track
        self.queues = {}

    # ------------------------------------------------------------------
    #     /musicpanel - Envia o painel com embed e botões (Permanente)
    # ------------------------------------------------------------------
    @app_commands.command(name="musicpanel", description="Exibe o painel de botões para controlar a música.")
    async def musicpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎶 Painel de Música",
            description=(
                "Utilize os botões abaixo para controlar a música:\n\n"
                "🔊 **Entrar**: Bot entra no seu canal de voz.\n"
                "▶️ **Play**: Abre um modal para tocar uma música (URL ou nome).\n"
                "⏯️ **Pause/Resume**: Pausa ou retoma a reprodução.\n"
                "⏭️ **Skip**: Pula a música atual.\n"
                "🛑 **Stop**: Para a música e limpa a fila.\n"
                "🎶 **Fila**: Exibe a fila de reprodução.\n"
                "🚪 **Sair**: Bot sai do canal de voz."
            ),
            color=discord.Color.blurple()
        )
        view = MusicView(self)
        # Envia o painel que permanece (não é temporário)
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    #     Funções chamadas pelos botões / modals
    # ------------------------------------------------------------------
    async def join_voice(self, interaction: discord.Interaction):
        user = interaction.user
        if not user.voice or not user.voice.channel:
            return await send_temporary_message(interaction, content="Você precisa estar em um canal de voz!")
        channel = user.voice.channel
        voice_client = interaction.guild.voice_client
        try:
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(channel)
            else:
                await channel.connect()
        except discord.Forbidden:
            return await send_temporary_message(interaction, content="❌ Não tenho permissão para entrar/mover para este canal de voz!")
        except Exception as e:
            return await send_temporary_message(interaction, content=f"❌ Erro ao conectar ao canal de voz: {e}")
        await send_temporary_message(interaction, content=f"Entrei no canal de voz: **{channel}**")

    async def play_music(self, interaction: discord.Interaction, search: str):
        guild = interaction.guild
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            if not interaction.user.voice or not interaction.user.voice.channel:
                return await send_temporary_message(interaction, content="Você não está em um canal de voz!")
            try:
                await interaction.user.voice.channel.connect()
            except discord.Forbidden:
                return await send_temporary_message(interaction, content="❌ Não tenho permissão para entrar no canal de voz!")
            except Exception as e:
                return await send_temporary_message(interaction, content=f"❌ Erro ao conectar ao canal de voz: {e}")
            voice_client = guild.voice_client

        await send_temporary_message(interaction, content="Buscando...")
        track = await self.get_track(search)
        if not track:
            return await send_temporary_message(interaction, content="❌ Não foi possível obter esta música.")

        queue = self.queues.setdefault(guild.id, [])
        queue.append(track)

        if not voice_client.is_playing():
            await self.play_next(guild)
            await send_temporary_message(interaction, content=f"🎶 Tocando agora: **{track.title}**")
        else:
            await send_temporary_message(interaction, content=f"Adicionado à fila: **{track.title}**")

    async def pause_resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return await send_temporary_message(interaction, content="O bot não está no canal de voz.")
        if voice_client.is_paused():
            voice_client.resume()
            await send_temporary_message(interaction, content="▶️ Música retomada.")
        elif voice_client.is_playing():
            voice_client.pause()
            await send_temporary_message(interaction, content="⏸️ Música pausada.")
        else:
            await send_temporary_message(interaction, content="Não há música tocando/pausada no momento.")

    async def skip_track(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            return await send_temporary_message(interaction, content="Não há música tocando para pular.")
        voice_client.stop()
        await send_temporary_message(interaction, content="⏭️ Música pulada!")

    async def stop_music(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            self.queues[interaction.guild.id] = []
            await send_temporary_message(interaction, content="🛑 Parei a música e limpei a fila!")
        else:
            await send_temporary_message(interaction, content="O bot não está tocando nada no momento.")

    async def show_queue(self, interaction: discord.Interaction):
        queue = self.queues.get(interaction.guild.id, [])
        if not queue:
            return await send_temporary_message(interaction, content="A fila está vazia.")
        desc = "\n".join(f"**{i+1}.** {t.title}" for i, t in enumerate(queue))
        embed = discord.Embed(
            title="🎶 Fila de Reprodução",
            description=desc,
            color=discord.Color.blue()
        )
        await send_temporary_message(interaction, embed=embed)

    async def leave_voice(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return await send_temporary_message(interaction, content="Não estou em nenhum canal de voz.")
        await voice_client.disconnect()
        self.queues[interaction.guild.id] = []
        await send_temporary_message(interaction, content="Saí do canal de voz!")

    # ------------------------------------------------------------------
    #   Lógica Interna para tocar a fila e extrair informações via yt-dlp
    # ------------------------------------------------------------------
    async def play_next(self, guild: discord.Guild):
        voice_client = guild.voice_client
        if not voice_client:
            return

        queue = self.queues.setdefault(guild.id, [])
        if len(queue) == 0:
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
                info = info["entries"][0]
                if not info:
                    return None
            return {
                "url": info["url"],
                "title": info.get("title"),
            }

# ======================================================================
#   SETUP DO COG
# ======================================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicButtonsCog(bot))
