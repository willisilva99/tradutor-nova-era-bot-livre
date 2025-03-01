import discord
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio
import aiohttp
import time

from db import SessionLocal, ServerStatusConfig  # Certifique-se de que ServerStatusConfig está definido no seu db.py

# Cache para reduzir chamadas à API
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
        self.status_task.start()
        self.intervalo = 10  # Intervalo padrão (minutos)
        self.ultimo_status_online = {}  # Para notificar quando o servidor ficar offline

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=10)
    async def status_task(self):
        """Atualiza o status de todos os servidores conforme intervalo definido."""
        with SessionLocal() as session:
            configs = session.query(ServerStatusConfig).all()
        for config in configs:
            embed = await self.fetch_status_embed(config.server_key)
            channel = self.bot.get_channel(int(config.channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(config.message_id))
                    await msg.edit(embed=embed)
                    
                    # Notificação de offline
                    online = embed.color == discord.Color.dark_green()
                    if config.guild_id in self.ultimo_status_online and not online and self.ultimo_status_online[config.guild_id]:
                        await channel.send("🔴 **Alerta:** O servidor está **OFFLINE**!")
                    self.ultimo_status_online[config.guild_id] = online
                    
                except Exception as e:
                    print(f"Erro ao editar mensagem de status para guild {config.guild_id}: {e}")

    async def fetch_status_embed(self, server_key: str) -> discord.Embed:
        """Consulta as APIs e monta um embed formatado."""
        if (cached := status_cache.get(server_key)):
            return cached
        
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(detail_url, headers=headers) as r:
                    detail_data = await r.json(content_type=None)
            except Exception as e:
                return discord.Embed(title="Erro ao obter dados do servidor", description=f"{e}", color=discord.Color.red())

        if not detail_data:
            return discord.Embed(title="Erro", description="API não retornou informações.", color=discord.Color.red())

        online_status = detail_data.get("is_online", "0") == "1"
        color = discord.Color.dark_green() if online_status else discord.Color.red()
        status_emoji = "🟢" if online_status else "🔴"
        
        embed = discord.Embed(title=f"{status_emoji} {detail_data.get('name', 'N/A')} - Status", color=color)
        embed.add_field(name="🌍 Localização", value=detail_data.get("location", "N/A"), inline=True)
        embed.add_field(name="🎮 Jogadores", value=f"{detail_data.get('players', 'N/A')}/{detail_data.get('maxplayers', 'N/A')}", inline=True)
        embed.add_field(name="⏳ Uptime", value=detail_data.get("uptime", "N/A"), inline=True)
        embed.set_footer(text=f"Atualizado em {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
        status_cache.set(server_key, embed)
        return embed

    @app_commands.command(name="serverstatus_config", description="Configura o status do servidor e canal de atualização.")
    @app_commands.checks.has_permissions(administrator=True)
    async def serverstatus_config(self, interaction: discord.Interaction, server_key: str, canal: discord.TextChannel):
        """Administra a configuração do servidor e canal onde o status será postado."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        msg = await canal.send("⏳ Carregando status do servidor...")
        with SessionLocal() as session:
            config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild_id)).first()
            if not config:
                config = ServerStatusConfig(guild_id=str(interaction.guild_id))
                session.add(config)
            config.server_key = server_key
            config.channel_id = str(canal.id)
            config.message_id = str(msg.id)
            session.commit()
        await interaction.followup.send("✅ Configuração salva!", ephemeral=True)

    @app_commands.command(name="serverstatus_show", description="Exibe o status do servidor agora mesmo.")
    async def serverstatus_show(self, interaction: discord.Interaction):
        """Mostra o status do servidor configurado."""
        await interaction.response.defer(thinking=True, ephemeral=False)
        with SessionLocal() as session:
            config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild_id)).first()
        if not config:
            await interaction.followup.send("⚠️ Nenhuma configuração encontrada. Use /serverstatus_config.", ephemeral=False)
            return
        embed = await self.fetch_status_embed(config.server_key)
        await interaction.followup.send(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatusCog(bot))
