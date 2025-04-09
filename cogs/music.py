import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import functools

# Se preferir usar yt-dlp:
# import yt_dlp as youtube_dl
import youtube_dl

# ==================================================
#   CONFIGURAÇÃO DO youtube_dl
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
#   Classe Track - armazena dados da música
# --------------------------------------------------
class Track:
    def __init__(self, source, title, url):
        self.source = source  # FFmpegPCMAudio
        self.title = title
        self.url = url

# ======================================================================
#   Modal para o "Play" - pergunta a URL/termo de busca
# ======================================================================
class PlaySongModal(discord.ui.Modal, title="Tocar Música"):
    query = discord.ui.TextInput(
        label="Nome / URL da música",
        style=discord.TextStyle.short,
        placeholder="Ex: https://youtube.com/..."
    )

    def __init__(self, cog, interaction: discord.Interaction):
        super().__init__()
        self.cog = cog
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        # Chama a função "play_music" do Cog, passando a query digitada
        await self.cog.play_music(interaction, self.query.value)

# ======================================================================
#   VIEW (Botões) para controlar a música
# ======================================================================
class MusicView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, emoji="🔊")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Botão para entrar no canal de voz do usuário."""
        await self.cog.join_voice(interaction)

    @discord.ui.button(label="Play", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre Modal para digitar a URL ou busca."""
        modal = PlaySongModal(self.cog, interaction)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.gray, emoji="⏯️")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pausa ou retoma a música atual."""
        await self.cog.pause_resume(interaction)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.gray, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pula a música atual."""
        await self.cog.skip_track(interaction)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Para a reprodução e limpa a fila."""
        await self.cog.stop_music(interaction)

    @discord.ui.button(label="Fila", style=discord.ButtonStyle.secondary, emoji="🎶")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mostra a fila."""
        await self.cog.show_queue(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bot sai do canal de voz."""
        await self.cog.leave_voice(interaction)


# ======================================================================
#   COG PRINCIPAL DE MÚSICA
# ======================================================================
class MusicButtonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Filas de reprodução por guild: guild_id -> [Track, Track, ...]
        self.queues = {}

    # ------------------------------------------------------------------
    #     /musicpanel - Envia o embed com a view de botões
    # ------------------------------------------------------------------
    @app_commands.command(name="musicpanel", description="Exibe um painel de botões para controlar a música.")
    async def musicpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎶 Painel de Música",
            description=(
                "Use os **botões** abaixo para **entrar**, tocar, pausar, pular, parar "
                "ou conferir a fila de músicas!\n"
                "• **Entrar**: Bot entra no seu canal.\n"
                "• **Play**: Abre um Modal para você digitar a música/URL.\n"
                "• **Pause/Resume**: Pausa ou retoma.\n"
                "• **Skip**: Pula a música atual.\n"
                "• **Stop**: Para tudo e limpa a fila.\n"
                "• **Fila**: Mostra as músicas na fila.\n"
                "• **Sair**: Bot sai do canal de voz."
            ),
            color=discord.Color.blurple()
        )
        view = MusicView(self)
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    #     Funções chamadas pelos BOTÕES / MODALS
    # ------------------------------------------------------------------
    async def join_voice(self, interaction: discord.Interaction):
        """Bot entra no canal de voz do usuário."""
        user = interaction.user
        if not user.voice or not user.voice.channel:
            return await interaction.response.send_message(
                "Você precisa estar em um canal de voz!",
                ephemeral=True
            )

        channel = user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_connected():
            await voice_client.move_to(channel)
        else:
            await channel.connect()

        await interaction.response.send_message(
            f"Entrei no canal de voz: **{channel}**",
            ephemeral=True
        )

    async def play_music(self, interaction: discord.Interaction, search: str):
        """Executa a lógica de tocar música (sem slash command)."""
        guild = interaction.guild
        voice_client = guild.voice_client

        if not voice_client or not voice_client.is_connected():
            # Tenta conectar
            if not interaction.user.voice or not interaction.user.voice.channel:
                return await interaction.followup.send(
                    "Você não está em um canal de voz!",
                    ephemeral=True
                )
            await interaction.user.voice.channel.connect()
            voice_client = guild.voice_client

        await interaction.followup.send("Buscando...", ephemeral=True)

        # Busca música
        track = await self.get_track(search)
        if not track:
            return await interaction.followup.send("❌ Não foi possível obter esta música.", ephemeral=True)

        queue = self.queues.setdefault(guild.id, [])
        queue.append(track)

        if not voice_client.is_playing():
            await self.play_next(guild)
            await interaction.followup.send(
                f"🎶 Tocando agora: **{track.title}**",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Adicionado à fila: **{track.title}**",
                ephemeral=True
            )

    async def pause_resume(self, interaction: discord.Interaction):
        """Pausa ou retoma a música."""
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return await interaction.response.send_message(
                "O bot não está no canal de voz.",
                ephemeral=True
            )

        if voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Música retomada.", ephemeral=True)
        elif voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Música pausada.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Não há música tocando/pausada no momento.",
                ephemeral=True
            )

    async def skip_track(self, interaction: discord.Interaction):
        """Pula a música atual."""
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            return await interaction.response.send_message(
                "Não há música tocando para pular.",
                ephemeral=True
            )
        voice_client.stop()
        await interaction.response.send_message("⏭️ Música pulada!", ephemeral=True)

    async def stop_music(self, interaction: discord.Interaction):
        """Para a música e limpa a fila."""
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            self.queues[interaction.guild.id] = []
            await interaction.response.send_message("🛑 Parei a música e limpei a fila!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "O bot não está tocando nada no momento.",
                ephemeral=True
            )

    async def show_queue(self, interaction: discord.Interaction):
        """Mostra a fila."""
        queue = self.queues.get(interaction.guild.id, [])
        if not queue:
            return await interaction.response.send_message("A fila está vazia.", ephemeral=True)
        desc = "\n".join(f"**{i+1}.** {t.title}" for i, t in enumerate(queue))
        embed = discord.Embed(
            title="🎶 Fila de Reprodução",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def leave_voice(self, interaction: discord.Interaction):
        """Sai do canal de voz."""
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return await interaction.response.send_message(
                "Não estou em nenhum canal de voz.",
                ephemeral=True
            )
        await voice_client.disconnect()
        self.queues[interaction.guild.id] = []
        await interaction.response.send_message("Saí do canal de voz!", ephemeral=True)

    # ------------------------------------------------------------------
    #     Funções Internas: tocar a fila, extrair info do Youtube
    # ------------------------------------------------------------------
    async def play_next(self, guild: discord.Guild):
        """Toca a próxima música da fila."""
        voice_client = guild.voice_client
        if not voice_client:
            return

        queue = self.queues.setdefault(guild.id, [])
        if len(queue) == 0:
            # Fila vazia => Opcional: desconectar
            # await voice_client.disconnect()
            return

        track = queue.pop(0)

        def after_playing(err):
            if err:
                print(f"Erro ao tocar: {err}")
            coro = self.play_next(guild)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except:
                pass

        voice_client.play(track.source, after=after_playing)
        # (Opcional) Enviar mensagem em algum canal fixo, se quiser

    async def get_track(self, search: str) -> Track:
        """Busca a música usando youtube_dl e retorna um Track."""
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
        """Extrai info usando youtube_dl."""
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


# >>>>>>> MUITO IMPORTANTE <<<<<<
# Ajuste aqui para a classe que você criou
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicButtonsCog(bot))
