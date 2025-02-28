import discord
from discord import app_commands
from discord.ext import commands, tasks

import asyncio
from sqlalchemy.orm import Session
from db import SessionLocal, ServerConfig

# Exemplo de biblioteca RCON (ajuste conforme a que preferir)
# from py_rcon import rcon


class SevenDaysCog(commands.Cog):
    """
    Cog para integração com 7 Days to Die (7DTD) via RCON.
    Permite adicionar servidores, consultar status, players etc.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Inicia uma task de "polling" para pegar infos do servidor periodicamente (chat bridge)
        self.check_chat_loop.start()

    def cog_unload(self):
        # Ao descarregar a cog, paramos a task
        self.check_chat_loop.cancel()

    # ============================================================
    # Comando: /7dtd addserver
    # Armazena as infos do servidor (IP, porta, senha RCON)
    # ============================================================
    @app_commands.command(name="7dtd_addserver", description="Adiciona um servidor 7DTD para este Discord.")
    @app_commands.describe(
        ip="IP do servidor 7DTD",
        port="Porta RCON do servidor",
        password="Senha RCON do servidor"
    )
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
        guild_id = str(interaction.guild_id)

        # Salva/atualiza no banco
        with SessionLocal() as session:
            # Se já existir config para essa guild, vamos atualizar ou criar uma nova
            config = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = ServerConfig(guild_id=guild_id)
                session.add(config)

            config.ip = ip
            config.port = port
            config.password = password
            session.commit()

        await interaction.response.send_message(
            f"Servidor 7DTD configurado!\nIP: `{ip}`, Porta: `{port}`", 
            ephemeral=True
        )

    # ============================================================
    # Comando: /7dtd channel
    # Define um canal para receber mensagens do servidor (chat bridge).
    # ============================================================
    @app_commands.command(name="7dtd_channel", description="Define canal para receber chat do servidor 7DTD.")
    async def set_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        guild_id = str(interaction.guild_id)

        with SessionLocal() as session:
            config = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not config:
                await interaction.response.send_message(
                    "Nenhum servidor 7DTD configurado. Use /7dtd_addserver primeiro.",
                    ephemeral=True
                )
                return
            
            config.channel_id = str(canal.id)
            session.commit()

        await interaction.response.send_message(
            f"Canal definido: {canal.mention}", 
            ephemeral=True
        )

    # ============================================================
    # Comando: /7dtd status
    # Mostra algumas infos do servidor: players, dia/hora, etc.
    # ============================================================
    @app_commands.command(name="7dtd_status", description="Exibe informações do servidor 7DTD.")
    async def show_status(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)

        with SessionLocal() as session:
            config = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
            if not config:
                await interaction.response.send_message(
                    "Nenhum servidor 7DTD configurado. Use /7dtd_addserver primeiro.",
                    ephemeral=True
                )
                return

            ip = config.ip
            port = config.port
            password = config.password

        # Aqui você chamaria o RCON para obter status do servidor (dia/hora, players, etc.)
        # Exemplo fictício de como poderia ser:
        """
        try:
            with rcon(ip, port, password) as client:
                # Comandos console 7d2d. Exemplo: "lp" para listar players, "gt" para game time...
                players_list = client.command("lp")  # <--- Ajuste ao que a biblioteca real usa
                game_time = client.command("gt")

                # Parse da resposta. Exemplo fictício:
                # "players_list" pode retornar algo como "EntityID  PlayerName"
                # "game_time" pode retornar algo como "Day 13, 08:45"
        except Exception as e:
            await interaction.response.send_message(
                f"Erro ao conectar no servidor: {e}",
                ephemeral=True
            )
            return
        """

        # Por enquanto, vamos simular dados:
        players_list = ["JogadorA", "JogadorB"]
        game_time = "Dia 13, 08:45"
        # Exemplo de Blood Moon a cada 7 dias, simular próxima no Dia 14:
        # Falta 1 dia e algumas horas, etc.

        embed = discord.Embed(
            title="7 Days to Die - Status",
            color=discord.Color.green()
        )
        embed.add_field(name="Servidor", value=f"{ip}:{port}", inline=False)
        embed.add_field(name="Jogadores Online", value=", ".join(players_list) if players_list else "Nenhum")
        embed.add_field(name="Dia/Hora", value=game_time, inline=False)
        embed.set_footer(text="Dados simulados. Integre com RCON para infos reais.")

        await interaction.response.send_message(embed=embed)

    # ============================================================
    # Exemplo de Tarefa para “chat bridge” (loop de polling)
    # ============================================================
    @tasks.loop(seconds=30)
    async def check_chat_loop(self):
        """
        Periodicamente, para cada servidor configurado, conecta via RCON,
        obtém as mensagens de chat (ou logs) e posta no canal definido.
        """
        await self.bot.wait_until_ready()

        # Buscar lista de configs
        with SessionLocal() as session:
            configs = session.query(ServerConfig).all()
        
        for cfg in configs:
            if not cfg.channel_id:
                continue  # se não definiram canal, pula

            channel = self.bot.get_channel(int(cfg.channel_id))
            if not channel:
                continue

            # Fazer a conexão RCON e buscar logs ou chat
            # Em 7DTD, pode haver um comando console tipo `loglevel` ou `getchat` etc.
            # Cada biblioteca RCON/7DTD é diferente, então aqui é só um rascunho.
            """
            try:
                with rcon(cfg.ip, cfg.port, cfg.password) as client:
                    # A ideia é: obter "novas" mensagens de chat desde a última verificação.
                    # Precisaria armazenar a data/hora do último fetch ou um offset...
                    chat_log = client.command("getchat 30")  # Exemplo fictício
                    # Parsear o resultado e extrair mensagens novas
                    # Ex: "09:15 [PlayerName]: Olá!"
            except Exception as e:
                print(f"Erro ao conectar RCON: {e}")
                continue
            
            # Se tiver mensagens novas, mandar no canal
            for msg in mensagens_novas:
                await channel.send(f"**[7DTD]** {msg}")
            """

            # Exemplo fictício (simulando):
            # Vamos supor que a cada 30s enviamos: "Exemplo de chat..."
            await channel.send("**[7DTD Chat Bridge - Exemplo]** Mensagem de chat simulada...")

    @check_chat_loop.before_loop
    async def before_check_chat(self):
        """
        Aguarda o bot ficar pronto antes de iniciar a loop.
        """
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SevenDaysCog(bot))
