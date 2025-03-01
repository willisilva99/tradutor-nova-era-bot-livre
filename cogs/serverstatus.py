import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.errors import NotFound
from sqlalchemy.orm import Session
import asyncio
import aiohttp
from datetime import datetime

from db import SessionLocal, ServerStatusConfig

class Cache:
    def __init__(self, ttl=60):
        self.ttl = ttl
        self.data = {}

    def get(self, key):
        if key in self.data:
            valor, timestamp = self.data[key]
            if (datetime.now().timestamp() - timestamp) < self.ttl:
                return valor
        return None

    def set(self, key, valor):
        self.data[key] = (valor, datetime.now().timestamp())

# Cache armazenando apenas o embed
embed_cache = Cache(ttl=60)

async def get_message(channel: discord.TextChannel, message_id: int):
    """
    Tenta recuperar a mensagem via fetch_message.
    Se não encontrar, procura no histórico do canal.
    """
    try:
        return await channel.fetch_message(message_id)
    except NotFound:
        async for msg in channel.history(limit=100):
            if msg.id == message_id:
                return msg
        raise NotFound(f"Mensagem {message_id} não encontrada no histórico.")

class ServerStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ultimo_status_online = {}
        self.status_task.start()

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=5)
    async def status_task(self):
        """Atualiza o status dos servidores a cada 5 minutos."""
        with SessionLocal() as session:
            configs = session.query(ServerStatusConfig).all()
        for config in configs:
            embed = await self.fetch_status_embed(config.server_key)
            channel = self.bot.get_channel(int(config.channel_id))
            if channel:
                try:
                    msg = await get_message(channel, int(config.message_id))
                    await msg.edit(embed=embed)
                except NotFound as nf:
                    print(f"[LOG] Mensagem não encontrada para guild {config.guild_id}: {repr(nf)}")
                    try:
                        msg = await channel.send(embed=embed)
                        with SessionLocal() as session:
                            cfg = session.query(ServerStatusConfig).filter_by(guild_id=str(config.guild_id)).first()
                            if cfg:
                                cfg.message_id = str(msg.id)
                                session.commit()
                        print(f"[LOG] Nova mensagem de status criada para guild {config.guild_id}")
                    except Exception as e2:
                        print(f"[ERROR] Erro ao criar nova mensagem para guild {config.guild_id}: {repr(e2)}")
                except Exception as e:
                    print(f"[ERROR] Erro ao editar mensagem de status para guild {config.guild_id}: {repr(e)}")
                
                # Envio de alertas de mudança de status
                online = (embed.color.value == discord.Color.green().value)
                if config.guild_id in self.ultimo_status_online:
                    if self.ultimo_status_online[config.guild_id] and not online:
                        await channel.send("🔴 **Alerta:** O servidor está **OFFLINE**!")
                    elif not self.ultimo_status_online[config.guild_id] and online:
                        await channel.send("🟢 **O servidor voltou a ficar ONLINE!**")
                self.ultimo_status_online[config.guild_id] = online

    async def fetch_status_embed(self, server_key: str):
        """
        Consulta a API do 7DTD para obter:
          - Detalhes do servidor (versão, nome, hostname, localização, IP, porta, jogadores, favoritos, uptime e status)
          - Total de votos e Top 3 votantes.
        Retorna um embed formatado.
        Utiliza cache para reduzir requisições repetidas.
        """
        cached = embed_cache.get(server_key)
        if cached is not None:
            return cached
        
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        votes_url = f"https://7daystodie-servers.com/api/?object=servers&element=votes&key={server_key}&format=json"
        voters_url = f"https://7daystodie-servers.com/api/?object=servers&element=voters&key={server_key}&month=current&format=json"
        
        try:
            async with aiohttp.ClientSession() as session:
                response = await asyncio.wait_for(session.get(detail_url, headers=headers), timeout=10)
                async with response:
                    detail_data = await response.json(content_type=None)
                
                response_votes = await asyncio.wait_for(session.get(votes_url, headers=headers), timeout=10)
                async with response_votes:
                    votes_data = await response_votes.json(content_type=None)
                votes_array = votes_data if isinstance(votes_data, list) else votes_data.get("votes", [])
                
                response_voters = await asyncio.wait_for(session.get(voters_url, headers=headers), timeout=10)
                async with response_voters:
                    voters_data = await response_voters.json(content_type=None)
                voters_list = voters_data if isinstance(voters_data, list) else voters_data.get("voters", [])
        except Exception as e:
            print(f"[ERROR] Erro na consulta da API (detail/votes/voters): {repr(e)}")
            erro_embed = discord.Embed(
                title="Erro ao obter dados do servidor", 
                description=repr(e), 
                color=discord.Color.red()
            )
            return erro_embed
        
        if not detail_data:
            erro_embed = discord.Embed(
                title="Erro", 
                description="A API não retornou informações.", 
                color=discord.Color.red()
            )
            return erro_embed
        
        server_version = detail_data.get("version", "N/A")
        server_name = detail_data.get("name", "N/A")
        hostname = detail_data.get("hostname", "N/A")
        location = detail_data.get("location", "N/A")
        maxplayers = detail_data.get("maxplayers", "N/A")
        players = detail_data.get("players", "N/A")
        favorited = detail_data.get("favorited", "N/A")
        uptime = detail_data.get("uptime", "N/A")
        ip = detail_data.get("address", "N/A")
        port = detail_data.get("port", "N/A")
        online_status = detail_data.get("is_online", "0") == "1"
        
        status_emoji = "🟢" if online_status else "🔴"
        status_text = "Online" if online_status else "Offline"
        color = discord.Color.green() if online_status else discord.Color.red()
        now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        
        total_votes = len(votes_array)
        top3 = sorted(voters_list, key=lambda v: int(v.get("votes", 0)), reverse=True)[:3]
        top3_str = ", ".join(f"{v.get('nickname', 'N/A')} ({v.get('votes', 0)})" for v in top3) if top3 else "N/A"
        
        embed = discord.Embed(
            title=f"{status_emoji} {server_name} - Status",
            color=color
        )
        embed.add_field(name="🌍 Localização", value=location, inline=True)
        embed.add_field(name="🔢 Versão", value=server_version, inline=True)
        embed.add_field(name="🔗 Hostname", value=hostname, inline=True)
        embed.add_field(name="🎮 Jogadores", value=f"{players}/{maxplayers}", inline=True)
        embed.add_field(name="⭐ Favoritos", value=f"{favorited}", inline=True)
        embed.add_field(name="🕒 Uptime", value=f"{uptime}%", inline=True)
        embed.add_field(name="📌 IP", value=f"{ip}:{port}", inline=True)
        embed.add_field(name="💻 Status", value=status_text, inline=True)
        embed.add_field(name="📊 Total de Votos", value=str(total_votes), inline=True)
        embed.add_field(name="🏆 Top 3 Votantes", value=top3_str, inline=False)
        embed.set_footer(text=f"Atualizado em: {now} | Atualiza a cada 5 minutos")
        
        embed_cache.set(server_key, embed)
        return embed

    @app_commands.command(name="serverstatus_config", description="Configura o status do servidor 7DTD para atualização automática.")
    async def serverstatus_config(self, interaction: discord.Interaction, server_key: str, canal: discord.TextChannel):
        """
        Configura o status do servidor:
          - Consulta a API, envia o embed inicial no canal especificado.
          - Salva a ServerKey, o canal e o ID da mensagem enviada no DB.
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            embed = await asyncio.wait_for(self.fetch_status_embed(server_key), timeout=10)
            msg = await canal.send(embed=embed)
            with SessionLocal() as session:
                config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
                if not config:
                    config = ServerStatusConfig(guild_id=str(interaction.guild.id))
                    session.add(config)
                config.server_key = server_key
                config.channel_id = str(canal.id)
                config.message_id = str(msg.id)
                session.commit()
            await interaction.followup.send("✅ Configuração salva! O status será atualizado automaticamente.", ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Erro no comando serverstatus_config: {repr(e)}")
            await interaction.followup.send(f"❌ Ocorreu um erro: {repr(e)}", ephemeral=True)

    @app_commands.command(name="serverstatus_show", description="Exibe o status do servidor 7DTD imediatamente.")
    async def serverstatus_show(self, interaction: discord.Interaction):
        """
        Exibe o status do servidor imediatamente.
        Se a mensagem já existir, edita-a; se não, cria uma nova e atualiza o registro.
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
            with SessionLocal() as session:
                config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
            if not config:
                await interaction.followup.send("Nenhuma configuração encontrada. Use /serverstatus_config para configurar.")
                return

            embed = await self.fetch_status_embed(config.server_key)
            channel = interaction.channel
            try:
                msg = await get_message(channel, int(config.message_id))
            except NotFound as nf:
                print(f"[LOG] Não foi possível buscar a mensagem registrada: {repr(nf)}")
                msg = await channel.send(embed=embed)
                with SessionLocal() as session:
                    config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
                    config.message_id = str(msg.id)
                    session.commit()

            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Erro no comando serverstatus_show: {repr(e)}")
            await interaction.followup.send(f"❌ Ocorreu um erro: {repr(e)}", ephemeral=True)

    @app_commands.command(name="serverstatus_remove", description="Remove a configuração de status do servidor 7DTD.")
    async def serverstatus_remove(self, interaction: discord.Interaction):
        """
        Remove a configuração de status:
          - Tenta deletar a mensagem de status (se existir).
          - Remove a configuração do banco de dados.
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            with SessionLocal() as session:
                config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
                if not config:
                    await interaction.followup.send("Nenhuma configuração encontrada.", ephemeral=True)
                    return
                channel = self.bot.get_channel(int(config.channel_id))
                if channel:
                    try:
                        msg = await channel.fetch_message(int(config.message_id))
                        await msg.delete()
                    except Exception as e:
                        print(f"[ERROR] Não foi possível deletar a mensagem: {repr(e)}")
                session.delete(config)
                session.commit()
            await interaction.followup.send("✅ Configuração removida e mensagem deletada (se encontrada).", ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Erro no comando serverstatus_remove: {repr(e)}")
            await interaction.followup.send(f"❌ Ocorreu um erro: {repr(e)}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatusCog(bot))
