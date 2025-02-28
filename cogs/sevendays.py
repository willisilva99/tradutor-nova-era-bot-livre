# cogs/sevendays.py
import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.orm import Session
import telnetlib
import threading
import asyncio

from db import SessionLocal, ServerConfig

# Dicionário global: guild_id -> TelnetConnection
active_connections = {}

class TelnetConnection:
    def __init__(self, guild_id, ip, port, password, channel_id, bot):
        self.guild_id = guild_id
        self.ip = ip
        self.port = port
        self.password = password
        self.channel_id = channel_id
        self.bot = bot

        self.telnet = None
        self.thread = None
        self.stop_flag = False
        self.lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            with self.lock:
                self.telnet = telnetlib.Telnet(self.ip, self.port, timeout=10)
                self.telnet.read_until(b"password:", timeout=5)
                self.telnet.write(self.password.encode("utf-8") + b"\r\n")
                self.telnet.read_until(b">", timeout=5)

            while not self.stop_flag:
                line = self.telnet.read_until(b"\n", timeout=1)
                if line:
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        self.handle_line(decoded)
        except Exception as e:
            print(f"[TelnetConnection][guild={self.guild_id}] Erro: {e}")
        print(f"[TelnetConnection][guild={self.guild_id}] Encerrada.")

    def handle_line(self, line: str):
        # Exemplo: se contiver “Chat (from ”, repassar pro canal
        if "Chat (from " in line or "GMSG" in line:
            if self.channel_id:
                ch = self.bot.get_channel(int(self.channel_id))
                if ch:
                    asyncio.run_coroutine_threadsafe(ch.send(f"[7DTD] {line}"), self.bot.loop)

    def stop(self):
        self.stop_flag = True
        with self.lock:
            if self.telnet:
                self.telnet.write(b"exit\r\n")
                self.telnet.close()
        if self.thread and self.thread.is_alive():
            self.thread.join()

    async def send_command(self, cmd: str, wait_prompt=True) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._send_blocking, cmd, wait_prompt)

    def _send_blocking(self, cmd: str, wait_prompt: bool) -> str:
        with self.lock:
            if not self.telnet:
                return "Conexão Telnet não iniciada."
            self.telnet.write(cmd.encode("utf-8") + b"\r\n")
            if wait_prompt:
                data = self.telnet.read_until(b">", timeout=3)
                return data.decode("utf-8", errors="ignore")
            else:
                return ""

class SevenDaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="7dtd_addserver", description="Adiciona ou atualiza um servidor 7DTD para este Discord.")
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild_id)
        with SessionLocal() as session:
            cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                cfg = ServerConfig(guild_id=guild_id)
                session.add(cfg)
            cfg.ip = ip
            cfg.port = port
            cfg.password = password
            session.commit()

        # Para antiga conexao se existir
        if guild_id in active_connections:
            active_connections[guild_id].stop()
            del active_connections[guild_id]

        # Cria nova
        channel_id = cfg.channel_id
        conn = TelnetConnection(guild_id, ip, port, password, channel_id, self.bot)
        active_connections[guild_id] = conn
        conn.start()

        await interaction.followup.send(
            f"Servidor 7DTD configurado!\nIP: `{ip}`, Porta: `{port}`",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_channel", description="Define canal para receber chat do servidor 7DTD.")
    async def set_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)

        with SessionLocal() as session:
            cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                await interaction.followup.send(
                    "Nenhum servidor configurado. Use /7dtd_addserver primeiro.",
                    ephemeral=True
                )
                return
            cfg.channel_id = str(canal.id)
            session.commit()

        # Se tiver conexão ativa, atualiza
        if guild_id in active_connections:
            active_connections[guild_id].channel_id = str(canal.id)

        await interaction.followup.send(
            f"Canal definido: {canal.mention}",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_test", description="Verifica a conexão chamando o comando 'version'.")
    async def test_connection(self, interaction: discord.Interaction):
        """
        Tenta enviar 'version'. Se a conexão não existir em active_connections,
        tentamos ler do DB e criar na hora. Se não houver DB, pedimos /7dtd_addserver.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        guild_id = str(interaction.guild_id)

        # 1) Se não existir no active_connections, tenta recriar do DB
        if guild_id not in active_connections:
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    # sem config no DB
                    await interaction.followup.send(
                        "Nenhum servidor cadastrado no DB. Use /7dtd_addserver primeiro.",
                        ephemeral=True
                    )
                    return

                # Cria a conexão
                conn = TelnetConnection(
                    guild_id=guild_id,
                    ip=cfg.ip,
                    port=cfg.port,
                    password=cfg.password,
                    channel_id=cfg.channel_id,
                    bot=self.bot
                )
                active_connections[guild_id] = conn
                conn.start()

        # 2) Agora existe
        conn = active_connections[guild_id]

        # 3) Manda "version"
        try:
            result = await conn.send_command("version")
            await interaction.followup.send(
                f"**Resultado:**\n```\n{result}\n```",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Erro ao executar comando: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SevenDaysCog(bot))
