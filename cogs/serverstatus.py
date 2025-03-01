import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio
import aiohttp
import time

from db import SessionLocal, ServerStatusConfig  # Certifique-se de que ServerStatusConfig está definido no seu db.py

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
          - Detalhes do servidor (nome, IP, porta, status e jogadores online)
          - Total de votos
          - Top 3 votantes
        Caso a API não retorne informações adequadas, exibe um embed de erro.
        """
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        votes_url = f"https://7daystodie-servers.com/api/?object=servers&element=votes&key={server_key}&format=json"
        voters_url = f"https://7daystodie-servers.com/api/?object=servers&element=voters&key={server_key}&month=current&format=json"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(detail_url, headers=headers) as r:
                    detail_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta detail: {e}")
                return discord.Embed(
                    title="Erro ao obter dados do servidor",
                    description=f"Detail: {e}",
                    color=discord.Color.red()
                )
            try:
                async with session.get(votes_url, headers=headers) as r:
                    votes_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta votes: {e}")
                return discord.Embed(
                    title="Erro ao obter dados de votos",
                    description=f"Votes: {e}",
                    color=discord.Color.red()
                )
            try:
                async with session.get(voters_url, headers=headers) as r:
                    voters_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta voters: {e}")
                return discord.Embed(
                    title="Erro ao obter dados de votantes",
                    description=f"Voters: {e}",
                    color=discord.Color.red()
                )

        if not detail_data:
            return discord.Embed(
                title="Erro ao obter dados do servidor",
                description="A API não retornou informações. Verifique a chave e tente novamente.",
                color=discord.Color.red()
            )

        # Extração dos dados conforme a estrutura fornecida pela API
        server_name = detail_data.get("name", "N/A")
        ip = detail_data.get("address", "N/A")
        port = detail_data.get("port", "N/A")
        # Jogadores online não consta na resposta; usamos "N/A"
        players = "N/A"
        max_players = "N/A"
        # Se não houver informação de status, assumimos online
        online_status = True
        status_text = "Online" if online_status else "Offline"

        # Para votos: usamos o array de votos; Total de votos será o tamanho desse array
        votes_array = votes_data.get("votes", [])
        total_votes = len(votes_array)

        # Para os top 3 votantes, ordenamos pelo timestamp (descendente)
        top3 = sorted(votes_array, key=lambda v: int(v.get("timestamp", 0)), reverse=True)[:3]
        top3_str = (
            ", ".join(f'{v.get("nickname", "N/A")} (Claimed: {v.get("claimed", "0")})' for v in top3)
            if top3 else "N/A"
        )

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
