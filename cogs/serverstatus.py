import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio
import aiohttp
import time

from db import SessionLocal, ServerStatusConfig

class Cache:
    def __init__(self, ttl=60):
        self.ttl = ttl
        self.data = {}

    def get(self, key):
        if key in self.data:
            valor, timestamp = self.data[key]
            if time.time() - timestamp < self.ttl:
                return valor
        return None

    def set(self, key, valor):
        self.data[key] = (valor, time.time())

status_cache = Cache(ttl=60)

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
            embed, view = await self.fetch_status_embed(config.server_key)
            channel = self.bot.get_channel(int(config.channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(config.message_id))
                    await msg.edit(embed=embed, view=view)
                    
                    # Verifica mudança de status com base no valor numérico da cor
                    online = (embed.color.value == discord.Color.green().value)
                    if config.guild_id in self.ultimo_status_online:
                        if self.ultimo_status_online[config.guild_id] and not online:
                            await channel.send("🔴 **Alerta:** O servidor está **OFFLINE**!")
                        elif not self.ultimo_status_online[config.guild_id] and online:
                            await channel.send("🟢 **O servidor voltou a ficar ONLINE!**")
                    self.ultimo_status_online[config.guild_id] = online
                except Exception as e:
                    print(f"Erro ao editar mensagem de status para guild {config.guild_id}: {e}")

    async def fetch_status_embed(self, server_key: str):
        """
        Consulta a API do 7DTD para obter os detalhes do servidor e constrói o embed e os botões.
        Utiliza cache para reduzir requisições repetidas.
        """
        # Verifica cache
        if (cached := status_cache.get(server_key)):
            return cached
        
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Aguarda a resposta com timeout
                response = await asyncio.wait_for(session.get(detail_url, headers=headers), timeout=10)
                async with response:
                    detail_data = await response.json(content_type=None)
        except Exception as e:
            print(f"Erro na consulta da API (detail): {e}")
            erro_embed = discord.Embed(
                title="Erro ao obter dados do servidor", 
                description=f"{e}", 
                color=discord.Color.red()
            )
            return erro_embed, discord.ui.View()
        
        if not detail_data:
            erro_embed = discord.Embed(
                title="Erro", 
                description="A API não retornou informações.", 
                color=discord.Color.red()
            )
            return erro_embed, discord.ui.View()
        
        # Extração dos dados
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
        
        # Define emoji e cor com base no status
        status_emoji = "🟢" if online_status else "🔴"
        color = discord.Color.green() if online_status else discord.Color.red()
        timestamp = time.strftime('%d/%m/%Y %H:%M:%S')

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
        embed.set_footer(text=f"Atualizado em: {timestamp}")
        
        # Criação dos botões
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="🌐 Votar no Servidor", 
            url=f"https://7daystodie-servers.com/server/{server_key}", 
            style=discord.ButtonStyle.link
        ))
        view.add_item(discord.ui.Button(
            label="🎮 Jogar Agora", 
            url=f"steam://connect/{ip}:{port}", 
            style=discord.ButtonStyle.link
        ))
        
        status_cache.set(server_key, (embed, view))
        return embed, view

    @app_commands.command(name="serverstatus_config", description="Configura o status do servidor 7DTD para atualização automática.")
    async def serverstatus_config(self, interaction: discord.Interaction, server_key: str, canal: discord.TextChannel):
        """
        Comando para configurar o status do servidor:
          - Consulta a API e envia o embed inicial no canal especificado.
          - Salva a ServerKey, o canal e o ID da mensagem enviada.
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            # Tenta obter o embed com timeout para evitar travamento
            embed, view = await asyncio.wait_for(self.fetch_status_embed(server_key), timeout=10)
            msg = await canal.send(embed=embed, view=view)
            # Atualiza o banco com os dados de configuração
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
            print("Erro no comando serverstatus_config:", e)
            await interaction.followup.send(f"❌ Ocorreu um erro: {e}", ephemeral=True)

    @app_commands.command(name="serverstatus_show", description="Exibe o status do servidor 7DTD imediatamente.")
    async def serverstatus_show(self, interaction: discord.Interaction):
        """
        Comando para exibir o status do servidor imediatamente.
        Caso o ID da mensagem não exista, envia uma nova mensagem e atualiza o registro.
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
            with SessionLocal() as session:
                config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
            if not config:
                await interaction.followup.send("Nenhuma configuração encontrada. Use /serverstatus_config para configurar.")
                return

            embed, view = await self.fetch_status_embed(config.server_key)
            channel = interaction.channel

            # Tenta buscar a mensagem de status já registrada
            try:
                msg = await channel.fetch_message(int(config.message_id))
            except Exception as e:
                print(f"Não foi possível buscar a mensagem registrada: {e}")
                msg = await channel.send(embed=embed, view=view)
                # Atualiza o ID da mensagem no banco
                with SessionLocal() as session:
                    config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild.id)).first()
                    config.message_id = str(msg.id)
                    session.commit()

            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print("Erro no comando serverstatus_show:", e)
            await interaction.followup.send(f"❌ Ocorreu um erro: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatusCog(bot))

