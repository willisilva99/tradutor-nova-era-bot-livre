import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.orm import Session
import telnetlib
import threading
import asyncio

# Importe também a classe e sessão do seu db.py
from db import SessionLocal, ServerConfig

# Um dicionário global que mapeia guild_id -> objeto TelnetConnection
active_connections = {}

class TelnetConnection:
    """
    Exemplo de classe para manter conexão Telnet com 7DTD.
    Aqui você poderia expandir para chat bridging etc.
    """
    def __init__(self, guild_id: str, ip: str, port: int, password: str, channel_id: str, bot: commands.Bot):
        self.guild_id = guild_id
        self.ip = ip
        self.port = port
        self.password = password
        self.channel_id = channel_id  # pode estar vazio se não definido
        self.bot = bot

        self.telnet = None
        self.thread = None
        self.stop_flag = False
        self.lock = threading.Lock()  # controle de acesso (leitura/escrita)

    def start(self):
        # Inicia a thread que conecta no Telnet e lê as mensagens
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            with self.lock:
                self.telnet = telnetlib.Telnet(self.ip, self.port, timeout=10)
                # Lê até aparecer algo tipo "password:"
                self.telnet.read_until(b"password:", timeout=5)
                # Envia a senha e \r\n
                self.telnet.write(self.password.encode("utf-8") + b"\r\n")
                # Espera o prompt final (pode variar, por ex. ">")
                self.telnet.read_until(b">", timeout=5)

            while not self.stop_flag:
                # Tenta ler linha a cada ~1s
                line = self.telnet.read_until(b"\n", timeout=1)
                if line:
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        self.handle_line(decoded)

        except Exception as e:
            print(f"[TelnetConnection][guild={self.guild_id}] Erro ao conectar/lêr Telnet: {e}")

        print(f"[TelnetConnection][guild={self.guild_id}] Conexão finalizada.")

    def handle_line(self, line: str):
        """
        Exemplo: se quiser implementar chat bridging, 
        verifique se a linha contém 'Chat (from ' ou 'GMSG' e poste no canal.
        """
        # Exemplo simples: se contiver "Chat", envia pro canal
        if "Chat (from " in line or "GMSG" in line:
            if self.channel_id:
                channel = self.bot.get_channel(int(self.channel_id))
                if channel:
                    # Como estamos numa thread, usamos run_coroutine_threadsafe p/ mandar msg no Discord
                    asyncio.run_coroutine_threadsafe(channel.send(f"[7DTD] {line}"), self.bot.loop)

    def stop(self):
        # Para a thread de leitura e encerra a conexão
        self.stop_flag = True
        with self.lock:
            if self.telnet:
                self.telnet.write(b"exit\r\n")
                self.telnet.close()
        if self.thread and self.thread.is_alive():
            self.thread.join()

    async def send_command(self, cmd: str, wait_prompt: bool = True) -> str:
        """
        Envia um comando telnet e retorna o output.
        Uso: await self.send_command("gettime")
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._send_blocking, cmd, wait_prompt)

    def _send_blocking(self, cmd, wait_prompt):
        with self.lock:
            if not self.telnet:
                return "Conexão Telnet não inicializada."
            self.telnet.write(cmd.encode("utf-8") + b"\r\n")
            if wait_prompt:
                data = self.telnet.read_until(b">", timeout=3)
                return data.decode("utf-8", errors="ignore")
            else:
                return ""

class SevenDaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="7dtd_addserver", description="Adiciona ou atualiza o servidor 7DTD neste servidor Discord.")
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
        """
        /7dtd_addserver ip:... port:... password:...

        Registra/atualiza no banco e inicia uma conexão Telnet.
        """
        # 1. Defer a resposta para evitar "O aplicativo não respondeu"
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild_id)

        # 2. Atualiza ou cria o registro no banco
        with SessionLocal() as session:
            config = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = ServerConfig(guild_id=guild_id)
                session.add(config)
            config.ip = ip
            config.port = port
            config.password = password
            session.commit()

        # 3. Para qualquer conexão prévia
        if guild_id in active_connections:
            active_connections[guild_id].stop()
            del active_connections[guild_id]

        # 4. Cria uma nova conexão Telnet e inicia a thread
        channel_id = config.channel_id  # se já existir
        conn = TelnetConnection(guild_id, ip, port, password, channel_id, self.bot)
        active_connections[guild_id] = conn
        conn.start()

        # 5. Envia a resposta final
        await interaction.followup.send(
            f"Servidor 7DTD configurado!\nIP: `{ip}`, Porta: `{port}`\nConexão Telnet iniciada (se IP/senha/porta estiverem corretos).",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_channel", description="Define canal para receber chat do servidor 7DTD.")
    async def set_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        """
        /7dtd_channel #canal
        Atualiza no DB e, se existir conexão Telnet, muda o channel_id para exibir logs.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild_id)
        with SessionLocal() as session:
            config = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not config:
                await interaction.followup.send(
                    "Nenhum servidor 7DTD configurado. Use /7dtd_addserver primeiro.",
                    ephemeral=True
                )
                return
            config.channel_id = str(canal.id)
            session.commit()

        # Se já temos uma conexão, atualiza
        if guild_id in active_connections:
            active_connections[guild_id].channel_id = str(canal.id)

        await interaction.followup.send(
            f"Canal definido: {canal.mention}",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_test", description="Envia comando 'version' para testar a conexão.")
    async def test_connection(self, interaction: discord.Interaction):
        """
        /7dtd_test -> Manda 'version' e retorna a saída do servidor (exemplo).
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild_id)
        if guild_id not in active_connections:
            await interaction.followup.send(
                "Nenhuma conexão ativa. Use /7dtd_addserver primeiro.", 
                ephemeral=True
            )
            return

        conn = active_connections[guild_id]
        try:
            # Envia o comando "version"
            result = await conn.send_command("version")
            # Retorna a saída para o usuário
            await interaction.followup.send(
                f"**Resposta do servidor:**\n```\n{result}\n```",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"Falha ao conectar/executar comando:\n{e}",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(SevenDaysCog(bot))
