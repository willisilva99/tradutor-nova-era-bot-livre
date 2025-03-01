import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio
import aiohttp
import time

from db import SessionLocal, ServerStatusConfig  # Certifique-se de que ServerStatusConfig está definido no db.py

class ServerStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.status_task.start()

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=10)
    async def status_task(self):
        """Atualiza o status de todos os servidores a cada 10 minutos."""
        with SessionLocal() as session:
            configs = session.query(ServerStatusConfig).all()
        for config in configs:
            embed = await self.fetch_status_embed(config.server_key)
            channel = self.bot.get_channel(int(config.channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(config.message_id))
                    await msg.edit(embed=embed)
                except Exception as e:
                    print(f"Erro ao editar mensagem de status para guild {config.guild_id}: {e}")

    async def fetch_status_embed(self, server_key: str) -> discord.Embed:
        """
        Consulta as APIs do 7DTD e constrói um embed com:
          - Nome, IP, Porta, status online/offline
          - Total de votos
          - Top 3 votantes
        Ajuste os campos conforme a resposta da API.
        """
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        votes_url = f"https://7daystodie-servers.com/api/?object=servers&element=votes&key={server_key}&format=json"
        voters_url = f"https://7daystodie-servers.com/api/?object=servers&element=voters&key={server_key}&month=all&format=json"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(detail_url) as r:
                    detail_data = await r.json()
            except Exception as e:
                detail_data = {}
                print(f"Erro na consulta detail: {e}")
            try:
                async with session.get(votes_url) as r:
                    votes_data = await r.json()
            except Exception as e:
                votes_data = {}
                print(f"Erro na consulta votes: {e}")
            try:
                async with session.get(voters_url) as r:
                    voters_data = await r.json()
            except Exception as e:
                voters_data = {}
                print(f"Erro na consulta voters: {e}")

        # Extraia dados do detail_data conforme a estrutura retornada pela API
        server_name = detail_data.get("serverName", "N/A")
        ip = detail_data.get("ip", "N/A")
        port = detail_data.get("port", "N/A")
        players = detail_data.get("players", 0)
        max_players = detail_data.get("maxPlayers", 0)
        online_status = detail_data.get("online", True)
        status_text = "Online" if online_status else "Offline"

        total_votes = votes_data.get("totalVotes", "N/A")

        # Processa os votantes
        voters_list = voters_data.get("voters", [])
        voters_sorted = sorted(voters_list, key=lambda v: v.get("votes", 0), reverse=True)
        top3 = voters_sorted[:3]
        top3_str = ", ".join(f'{v.get("username", "N/A")} ({v.get("votes", 0)})' for v in top3) if top3 else "N/A"

        embed = discord.Embed(
            title=f"Status do Servidor: {server_name}",
            color=discord.Color.dark_green() if online_status else discord.Color.red()
        )
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="IP:Porta", value=f"{ip}:{port}", inline=True)
        embed.add_field(name="Jogadores Online", value=f"{players}/{max_players}", inline=True)
        embed.add_field(name="Total de Votos", value=total_votes, inline=True)
        embed.add_field(name="Top 3 Votantes", value=top3_str, inline=False)
        embed.set_footer(text="Atualizado em " + time.strftime("%d/%m/%Y %H:%M:%S"))
        return embed

    @app_commands.command(name="serverstatus_config", description="Configura o status do servidor 7DTD para atualização automática.")
    async def serverstatus_config(self, interaction: discord.Interaction, server_key: str, canal: discord.TextChannel):
        """
        Configura o status do servidor, salvando a ServerKey e o canal onde o status será postado.
        O bot envia uma mensagem inicial que será editada automaticamente a cada 10 minutos.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        msg = await canal.send("Carregando status do servidor...")
        with SessionLocal() as session:
            config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild_id)).first()
            if not config:
                config = ServerStatusConfig(guild_id=str(interaction.guild_id))
                session.add(config)
            config.server_key = server_key
            config.channel_id = str(canal.id)
            config.message_id = str(msg.id)
            session.commit()
        await interaction.followup.send("Configuração de status atualizada!", ephemeral=True)

    @app_commands.command(name="serverstatus_show", description="Exibe o status do servidor 7DTD imediatamente.")
    async def serverstatus_show(self, interaction: discord.Interaction):
        """
        Atualiza e exibe imediatamente o status do servidor conforme a configuração salva.
        """
        await interaction.response.defer(thinking=True, ephemeral=False)
        with SessionLocal() as session:
            config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild_id)).first()
        if not config:
            await interaction.followup.send("Nenhuma configuração encontrada. Use /serverstatus_config para configurar.", ephemeral=False)
            return
        embed = await self.fetch_status_embed(config.server_key)
        await interaction.followup.send(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatusCog(bot))
