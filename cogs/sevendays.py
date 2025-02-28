# cogs/sevendays.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
from db import SessionLocal, ServerConfig
# from py_rcon import rcon  # Se quiser usar alguma lib RCON

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
        
        # Aqui chamaria RCON de fato. Exemplo fictício:
        # with rcon(ip, port, password) as client:
        #     status = client.command("status_command")

        embed = discord.Embed(title="7DTD Status", description="Exemplo de status", color=discord.Color.green())
        embed.add_field(name="Server", value=f"{ip}:{port}", inline=False)
        embed.add_field(name="Players Online", value="Exemplo: 3", inline=True)
        embed.add_field(name="Dia/Hora", value="Dia 15, 10:47", inline=True)

        await interaction.response.send_message(embed=embed)

    @tasks.loop(seconds=60)
    async def check_chat_loop(self):
        await self.bot.wait_until_ready()
        with SessionLocal() as session:
            configs = session.query(ServerConfig).all()

        for cfg in configs:
            if not cfg.channel_id:
                continue
            channel = self.bot.get_channel(int(cfg.channel_id))
            if not channel:
                continue
            # Lógica de RCON para pegar chat
            # ...
            # Exemplo fictício:
            # new_messages = client.command("getchat")
            # if new_messages:
            #     for msg in new_messages:
            #         await channel.send(f"[7DTD] {msg}")
            await channel.send(f"[Exemplo] Checando chat do servidor {cfg.ip}:{cfg.port}...")

async def setup(bot):
    await bot.add_cog(SevenDaysCog(bot))
