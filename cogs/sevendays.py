# cogs/sevendays.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
from db import SessionLocal, ServerConfig

# Se estiver usando a biblioteca py-rcon (pip install py-rcon)
from rcon import Client

class SevenDaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_chat_loop.start()

    def cog_unload(self):
        self.check_chat_loop.cancel()

    @app_commands.command(name="7dtd_addserver", description="Adiciona um servidor 7DTD para este Discord.")
    async def addserver(self, interaction: discord.Interaction, ip: str, port: int, password: str):
        guild_id = str(interaction.guild_id)
        with SessionLocal() as session:
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

        # Tentamos conectar e confirmar se o servidor responde
        try:
            with Client(ip, port, passwd=password) as client:
                # Exemplos de comando RCON:
                # Vamos chamar 'version' só pra garantir que retornou algo
                version_info = client.run("version")
                # Você também poderia chamar outros comandos como:
                # game_time = client.run("gt")  # se existir
                # players = client.run("lp")    # se existir
        except Exception as e:
            # Falhou a conexão: retornamos erro
            await interaction.response.send_message(
                f"❌ Não foi possível conectar ao servidor `{ip}:{port}`.\n**Erro:** {e}",
                ephemeral=True
            )
            return

        # Se chegou até aqui, significa que a conexão funcionou e a gente pegou algo em version_info
        embed = discord.Embed(
            title="7DTD Status",
            description="**Conexão estabelecida com sucesso!**",
            color=discord.Color.green()
        )
        embed.add_field(name="Servidor (IP:Porta)", value=f"{ip}:{port}", inline=False)
        embed.add_field(name="Resposta do comando 'version':", value=version_info, inline=False)
        # Caso queira exibir mais dados, você pode chamar outros comandos e adicionar mais fields

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(seconds=60)
    async def check_chat_loop(self):
        """
        Esta função roda a cada 60 segundos para buscar mensagens do servidor
        e postar no canal designado. Aqui é só um exemplo simples que manda
        uma mensagem 'checando chat...' sem de fato implementar RCON.
        """
        await self.bot.wait_until_ready()
        with SessionLocal() as session:
            configs = session.query(ServerConfig).all()

        for cfg in configs:
            if not cfg.channel_id:
                continue
            channel = self.bot.get_channel(int(cfg.channel_id))
            if not channel:
                continue

            # Caso queira de fato implementar chat bridging:
            # try:
            #     with Client(cfg.ip, cfg.port, passwd=cfg.password) as client:
            #         new_messages = client.run("getchat")
            #         # Parse e poste no canal
            # except:
            #     pass

            await channel.send(f"[Exemplo] Checando chat do servidor {cfg.ip}:{cfg.port}...")

async def setup(bot):
    await bot.add_cog(SevenDaysCog(bot))
