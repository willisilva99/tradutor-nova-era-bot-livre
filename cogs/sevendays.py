# cogs/sevendays.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
from db import SessionLocal, ServerConfig

import telnetlib
import threading
import asyncio

active_connections = {}  # guild_id -> TelnetConnection

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

        self.lock = threading.Lock()  # pra evitar conflito entre leitura continua e send_command

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        try:
            with self.lock:
                self.telnet = telnetlib.Telnet(self.ip, self.port, timeout=10)
                self.telnet.read_until(b"password:")
                self.telnet.write(self.password.encode("utf-8") + b"\r\n")
                self.telnet.read_until(b">", timeout=5)

            while not self.stop_flag:
                # Lê linha a cada ~1s
                line = self.telnet.read_until(b"\n", timeout=1)
                if line:
                    line_decoded = line.decode("utf-8", errors="ignore").strip()
                    if line_decoded:
                        self.handle_line(line_decoded)
        except Exception as e:
            print(f"[{self.guild_id}] TelnetConnection erro: {e}")
        print(f"[{self.guild_id}] TelnetConnection finalizada.")

    def stop(self):
        self.stop_flag = True
        with self.lock:
            if self.telnet:
                self.telnet.write(b"exit\r\n")
                self.telnet.close()
        if self.thread:
            self.thread.join()

    def handle_line(self, line):
        # Exemplo: se ver 'Chat (from ' ou 'GMSG'
        if "Chat (from " in line or "GMSG" in line:
            # Manda para canal
            if self.channel_id:
                ch = self.bot.get_channel(int(self.channel_id))
                if ch:
                    # usar run_coroutine_threadsafe pois estamos fora da thread principal
                    asyncio.run_coroutine_threadsafe(ch.send(line), self.bot.loop)

    async def send_command(self, cmd, wait_prompt=True):
        """Envia comando e retorna output. Bloqueia a thread. Uso: await conn.send_command("gettime")"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._send_command_blocking, cmd, wait_prompt)

    def _send_command_blocking(self, cmd, wait_prompt):
        with self.lock:
            self.telnet.write(cmd.encode("utf-8") + b"\r\n")
            if wait_prompt:
                data = self.telnet.read_until(b">", timeout=3)
                return data.decode("utf-8", errors="ignore")
            else:
                return ""

class SevenDaysCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="7dtd_addserver", description="Adiciona/atualiza um servidor 7DTD para este Discord.")
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
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

        # Se já existe conexão, paramos
        if guild_id in active_connections:
            active_connections[guild_id].stop()
            del active_connections[guild_id]

        # Precisamos do channel_id se já definido
        channel_id = cfg.channel_id
        # Cria e inicia
        conn = TelnetConnection(guild_id, ip, port, password, channel_id, self.bot)
        active_connections[guild_id] = conn
        conn.start()

        await interaction.response.send_message(
            f"Servidor 7DTD configurado!\nIP: `{ip}`, Porta: `{port}`\nTentando conectar...",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_channel", description="Define canal para receber chat do servidor 7DTD.")
    async def set_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        guild_id = str(interaction.guild_id)
        with SessionLocal() as session:
            cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                await interaction.response.send_message(
                    "Nenhum servidor 7DTD configurado. Use /7dtd_addserver primeiro.",
                    ephemeral=True
                )
                return
            cfg.channel_id = str(canal.id)
            session.commit()

        # Se existir conexão, atualiza
        if guild_id in active_connections:
            active_connections[guild_id].channel_id = str(canal.id)

        await interaction.response.send_message(
            f"Canal definido: {canal.mention}", 
            ephemeral=True
        )

    @app_commands.command(name="7dtd_time", description="Mostra dia/hora do servidor (exemplo).")
    async def show_time(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in active_connections:
            await interaction.response.send_message("Nenhuma conexão ativa. Use /7dtd_addserver primeiro.", ephemeral=True)
            return

        conn = active_connections[guild_id]
        response = await conn.send_command("gettime")
        await interaction.response.send_message(
            f"Resposta do servidor:\n```\n{response}\n```",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(SevenDaysCog(bot))
