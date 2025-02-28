import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio
import telnetlib
import threading
import re

from db import SessionLocal, ServerConfig

# Dicionário global para armazenar conexões Telnet: guild_id -> TelnetConnection
active_connections = {}

class TelnetConnection:
    """
    Classe responsável por manter a conexão Telnet com o servidor 7DTD.
    Permite enviar comandos e ler outputs.
    """
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
        self.last_line = None  # Para evitar duplicatas

    def start(self):
        """Inicia a thread que conecta e fica lendo as linhas do telnet."""
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        """Loop da thread que conecta ao Telnet e lê as linhas continuamente."""
        try:
            with self.lock:
                self.telnet = telnetlib.Telnet(self.ip, self.port, timeout=10)
                # Espera prompt de senha
                self.telnet.read_until(b"password:", timeout=5)
                # Envia a senha
                self.telnet.write(self.password.encode("utf-8") + b"\r\n")
                # Espera prompt final (por exemplo, ">")
                self.telnet.read_until(b">", timeout=5)

            while not self.stop_flag:
                line = self.telnet.read_until(b"\n", timeout=1)
                if line:
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        self.handle_line(decoded)
        except Exception as e:
            print(f"[TelnetConnection][guild={self.guild_id}] Erro Telnet: {e}")
        print(f"[TelnetConnection][guild={self.guild_id}] Conexão encerrada.")

    def handle_line(self, line: str):
        """
        Processa as linhas de saída do servidor e formata mensagens de eventos:
        
        • Se a linha corresponder a uma mensagem de chat no formato:
            Chat (from 'Steam_xxx', entity id '...', to 'Global'): 'Nome': Mensagem
          formata como: 💬 **[CHAT] Nome**: Mensagem

        • Se corresponder a uma morte:
            GMSG: Player 'Nome' died
          formata como: 💀 **[CHAT] Nome** morreu

        • Se corresponder a saída:
            GMSG: Player 'Nome' left the game
          formata como: 🚪 **[CHAT] Nome** saiu do jogo

        • Se corresponder a entrada (join ou login):
            GMSG: Player 'Nome' joined the game
            ou
            RequestToEnterGame: .../Nome
          formata como: 🟢 **[CHAT] Nome** entrou no jogo

        Caso não bata nenhum padrão, envia a linha original.
        """
        # Evita duplicatas
        if self.last_line == line:
            return
        self.last_line = line

        formatted = None

        # Verifica morte
        death_pattern = r"GMSG: Player '([^']+)' died"
        m = re.search(death_pattern, line)
        if m:
            name = m.group(1)
            formatted = f"💀 **[CHAT] {name}** morreu"
        
        # Verifica saída
        if not formatted:
            leave_pattern = r"GMSG: Player '([^']+)' left the game"
            m = re.search(leave_pattern, line)
            if m:
                name = m.group(1)
                formatted = f"🚪 **[CHAT] {name}** saiu do jogo"
        
        # Verifica entrada (join)
        if not formatted:
            join_pattern = r"GMSG: Player '([^']+)' joined the game"
            m = re.search(join_pattern, line)
            if m:
                name = m.group(1)
                formatted = f"🟢 **[CHAT] {name}** entrou no jogo"
        
        # Verifica login (RequestToEnterGame)
        if not formatted:
            login_pattern = r"RequestToEnterGame: [^/]+/([^'\s]+)"
            m = re.search(login_pattern, line)
            if m:
                name = m.group(1)
                formatted = f"🟢 **[CHAT] {name}** entrou no jogo"
        
        # Verifica mensagem de chat padrão
        if not formatted and "Chat (from " in line:
            chat_pattern = r"Chat \(from '[^']+', entity id '[^']+', to '[^']+'\):\s*'([^']+)':\s*(.*)"
            m = re.search(chat_pattern, line)
            if m:
                name = m.group(1)
                message = m.group(2)
                formatted = f"💬 **[CHAT] {name}**: {message}"
        
        # Se nenhum padrão bater, usa a linha original
        if not formatted:
            formatted = line

        if self.channel_id:
            channel = self.bot.get_channel(int(self.channel_id))
            if channel:
                asyncio.run_coroutine_threadsafe(
                    channel.send(formatted), self.bot.loop
                )

    def stop(self):
        """Para a thread e fecha a conexão."""
        self.stop_flag = True
        with self.lock:
            if self.telnet:
                self.telnet.write(b"exit\r\n")
                self.telnet.close()
        if self.thread and self.thread.is_alive():
            self.thread.join()

    async def send_command(self, cmd: str, wait_prompt=True) -> str:
        """
        Envia um comando de forma assíncrona, bloqueando numa thread separada.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._send_blocking, cmd, wait_prompt)

    def _send_blocking(self, cmd: str, wait_prompt: bool) -> str:
        """Manda comando e lê a resposta (bloqueia a thread)."""
        with self.lock:
            if not self.telnet:
                return "Conexão Telnet não iniciada."
            self.telnet.write(cmd.encode("utf-8") + b"\r\n")
            if not wait_prompt:
                return ""
            try:
                data = self.telnet.read_until(b">", timeout=3)
                return data.decode("utf-8", errors="ignore")
            except EOFError:
                return "EOF durante leitura"

class SevenDaysCog(commands.Cog):
    """
    Cog que contém os comandos relacionados ao 7DTD:
    - /7dtd_addserver
    - /7dtd_channel
    - /7dtd_test
    - /7dtd_bloodmoon
    - /7dtd_players
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="7dtd_addserver", description="Adiciona ou atualiza um servidor 7DTD para este Discord.")
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
        """Registra/atualiza ip, porta e senha para este guild no DB e inicia a conexão Telnet."""
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

        if guild_id in active_connections:
            active_connections[guild_id].stop()
            del active_connections[guild_id]

        channel_id = cfg.channel_id  # Pode estar vazio se não definido
        conn = TelnetConnection(guild_id, ip, port, password, channel_id, self.bot)
        active_connections[guild_id] = conn
        conn.start()

        await interaction.followup.send(
            f"Servidor 7DTD configurado!\nIP: `{ip}`, Porta: `{port}`",
            ephemeral=True
        )

    @app_commands.command(name="7dtd_channel", description="Define canal para receber chat do servidor 7DTD.")
    async def set_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        """Define o canal de chat bridging/logs do 7DTD."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)
        with SessionLocal() as session:
            cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                return
            cfg.channel_id = str(canal.id)
            session.commit()

        if guild_id in active_connections:
            active_connections[guild_id].channel_id = str(canal.id)

        await interaction.followup.send(f"Canal definido: {canal.mention}", ephemeral=True)

    @app_commands.command(name="7dtd_test", description="Testa a conexão chamando o comando 'version'.")
    async def test_connection(self, interaction: discord.Interaction):
        """Executa 'version' para verificar a conexão."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)
        if guild_id not in active_connections:
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                    return
                conn = TelnetConnection(guild_id, cfg.ip, cfg.port, cfg.password, cfg.channel_id, self.bot)
                active_connections[guild_id] = conn
                conn.start()

        conn = active_connections[guild_id]
        try:
            result = await conn.send_command("version")
            await interaction.followup.send(f"**Resposta do servidor:**\n```\n{result}\n```", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Erro ao executar 'version': {e}", ephemeral=True)

    @app_commands.command(name="7dtd_bloodmoon", description="Mostra quando ocorre a próxima lua de sangue.")
    async def bloodmoon_status(self, interaction: discord.Interaction):
        """
        Chama 'gettime' e faz parse de "Day 14, 12:34" para calcular a próxima lua de sangue.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)
        if guild_id not in active_connections:
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                    return
                conn = TelnetConnection(guild_id, cfg.ip, cfg.port, cfg.password, cfg.channel_id, self.bot)
                active_connections[guild_id] = conn
                conn.start()
        conn = active_connections[guild_id]
        try:
            response = await conn.send_command("gettime")
        except Exception as e:
            await interaction.followup.send(f"Erro ao obter horário do servidor: {e}", ephemeral=True)
            return

        day = None
        hour = None
        minute = 0
        for line in response.splitlines():
            line = line.strip()
            if line.startswith("Day "):
                parts = line.replace("Day ", "").split(",")
                if len(parts) == 2:
                    try:
                        day = int(parts[0].strip())
                        hm = parts[1].strip().split(":")
                        if len(hm) == 2:
                            hour = int(hm[0])
                            minute = int(hm[1])
                    except:
                        pass

        if day is None or hour is None:
            await interaction.followup.send(f"Não foi possível parsear o horário:\n```\n{response}\n```", ephemeral=True)
            return

        horde_freq = 7
        daysFromHorde = day % horde_freq
        message = f"Hoje é **Dia {day}, {hour:02d}:{minute:02d}** no servidor."
        if daysFromHorde == 0:
            if hour >= 22 or hour < 4:
                message += "\n**A horda está acontecendo agora!**"
            elif hour < 22:
                hrs_left = 22 - hour
                message += f"\n**A horda começa em {hrs_left} hora(s).**"
            else:
                next_day = day + 7
                message += f"\nA horda de hoje já passou! Próxima no **Dia {next_day}**."
        else:
            days_to_horde = horde_freq - daysFromHorde
            next_horde_day = day + days_to_horde
            message += f"\nPróxima lua de sangue no **Dia {next_horde_day}** (em {days_to_horde} dia(s))."
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(name="7dtd_players", description="Lista quantos/quais jogadores estão online no 7DTD.")
    async def players_online(self, interaction: discord.Interaction):
        """
        Executa "listplayers" para obter nomes de jogadores online e exibe num embed.
        Remove duplicatas e exibe o resultado no formato:
          Total of X in the game
          **Lista**: Nome1, Nome2, ...
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)
        if guild_id not in active_connections:
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                    return
                conn = TelnetConnection(guild_id, cfg.ip, cfg.port, cfg.password, cfg.channel_id, self.bot)
                active_connections[guild_id] = conn
                conn.start()
        conn = active_connections[guild_id]
        try:
            response = await conn.send_command("listplayers")
        except Exception as e:
            await interaction.followup.send(f"Erro ao executar comando listplayers: {e}", ephemeral=True)
            return

        lines = response.splitlines()
        total_msg = None
        player_names = set()  # Usamos set para evitar duplicatas

        for line in lines:
            line = line.strip()
            if line.startswith("Total of "):
                total_msg = line
            elif "EntityID" in line:
                continue  # Ignora cabeçalho
            else:
                # Supomos que o formato seja: "189 John ..." onde a segunda coluna é o nome
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name:
                        player_names.add(name)

        if total_msg is None:
            total_msg = "Não encontrei a contagem total de players."
        if player_names:
            players_str = ", ".join(sorted(player_names))
        else:
            players_str = "Nenhum player listado."

        embed = discord.Embed(
            title="Jogadores Online",
            description=f"{total_msg}\n\n**Lista**: {players_str}",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    """
    Função de inicialização da Cog.
    No seu main.py, faça: await bot.load_extension("cogs.sevendays")
    """
    await bot.add_cog(SevenDaysCog(bot))
