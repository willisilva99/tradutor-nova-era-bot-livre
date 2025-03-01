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
        self.status_task.start()
        self.intervalo = 10  # Intervalo padrão (minutos)
        self.ultimo_status_online = {}

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=10)
    async def status_task(self):
        with SessionLocal() as session:
            configs = session.query(ServerStatusConfig).all()
        for config in configs:
            embed, view = await self.fetch_status_embed(config.server_key)
            channel = self.bot.get_channel(int(config.channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(config.message_id))
                    await msg.edit(embed=embed, view=view)
                    
                    online = embed.color == discord.Color.green()
                    if config.guild_id in self.ultimo_status_online and not online and self.ultimo_status_online[config.guild_id]:
                        await channel.send("🔴 **Alerta:** O servidor está **OFFLINE**!")
                    elif config.guild_id in self.ultimo_status_online and online and not self.ultimo_status_online[config.guild_id]:
                        await channel.send("🟢 **O servidor voltou a ficar ONLINE!**")
                    
                    self.ultimo_status_online[config.guild_id] = online
                except Exception as e:
                    print(f"Erro ao editar mensagem de status para guild {config.guild_id}: {e}")

    async def fetch_status_embed(self, server_key: str):
        if (cached := status_cache.get(server_key)):
            return cached
        
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(detail_url, headers=headers) as r:
                    detail_data = await r.json(content_type=None)
            except Exception as e:
                return discord.Embed(title="Erro ao obter dados do servidor", description=f"{e}", color=discord.Color.red()), None

        if not detail_data:
            return discord.Embed(title="Erro", description="API não retornou informações.", color=discord.Color.red()), None

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
        color = discord.Color.green() if online_status else discord.Color.red()
        timestamp = time.strftime('%d/%m/%Y %H:%M:%S')

        embed = discord.Embed(title=f"{status_emoji} {server_name} - Status", color=color)
        embed.add_field(name="🌍 Localização", value=location, inline=True)
        embed.add_field(name="🔢 Versão", value=server_version, inline=True)
        embed.add_field(name="🔗 Hostname", value=hostname, inline=True)
        embed.add_field(name="🎮 Jogadores", value=f"{players}/{maxplayers}", inline=True)
        embed.add_field(name="⭐ Favoritos", value=favorited, inline=True)
        embed.add_field(name="🕒 Uptime", value=f"{uptime}%", inline=True)
        embed.add_field(name="📌 IP", value=f"{ip}:{port}", inline=True)
        embed.set_footer(text=f"Próxima atualização: {timestamp}")
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🌐 Votar no Servidor", url=f"https://7daystodie-servers.com/server/{server_key}", style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label="🎮 Jogar Agora", url=f"steam://connect/{ip}:{port}", style=discord.ButtonStyle.link))
        
        status_cache.set(server_key, (embed, view))
        return embed, view
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Comandos de Slash sincronizados!")

    @app_commands.command(name="serverstatus_show", description="Exibe o status do servidor agora mesmo.")
    async def serverstatus_show(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)
        with SessionLocal() as session:
            config = session.query(ServerStatusConfig).filter_by(guild_id=str(interaction.guild_id)).first()
        if not config:
            await interaction.followup.send("⚠️ Nenhuma configuração encontrada. Use /serverstatus_config.", ephemeral=False)
            return
        embed, view = await self.fetch_status_embed(config.server_key)
        if not config.message_id:
            msg = await interaction.followup.send(embed=embed, view=view, ephemeral=False)
            with SessionLocal() as session:
                config.message_id = str(msg.id)
                session.commit()
        else:
            channel = self.bot.get_channel(int(config.channel_id))
            msg = await channel.fetch_message(int(config.message_id))
            await msg.edit(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatusCog(bot))
