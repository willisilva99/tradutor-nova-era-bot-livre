import json
import os
import re
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

CONFIG_PATH = "configs/recruitment_config.json"
DATA_PATH = "configs/recruitment_data.json"

class RecruitmentCog(commands.Cog):
    """Cog para gerenciar anúncios de recrutamento em canal configurado e filtrar mensagens."""

    def __init__(self, bot):
        self.bot = bot
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

        # Carrega canal de recrutamento por guild
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

        # Mensagens tutorial pendentes para apagar
        self.tutorials = {}  # {channel_id: tutorial_msg_id}

    def save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # Comando para definir canal de recrutamento
    @app_commands.command(name="set_recruit_channel", description="Define o canal de recrutamento.")
    @app_commands.describe(channel="Canal onde recrutamentos serão permitidos")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Você precisa da permissão Gerenciar Servidor.", ephemeral=True)

        self.config[str(interaction.guild.id)] = channel.id
        self.save_config()
        await interaction.response.send_message(f"✅ Canal de recrutamento definido: {channel.mention}", ephemeral=True)

    # Listener para filtrar mensagens
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id = str(message.guild.id) if message.guild else None
        channel_id = self.config.get(guild_id)
        if not channel_id or message.channel.id != channel_id:
            return

        # Padrão básico: precisa conter 'recrutando' ou 'buscando'
        content = message.content.lower()
        if not re.search(r"\b(recrutando|buscando)\b", content):
            try:
                await message.delete()
            except discord.Forbidden:
                return

            # envia tutorial e programa remoção
            tutorial = ("📢 **Como recrutar ou buscar clã**
"
                        "Use o comando `/recruit`:
"
                        "• `/recruit recrutando <nome_clan> <descrição>` para oferecer vagas
"
                        "• `/recruit buscando <nome_clan> <descrição>` para procurar clã
")
            sent = await message.channel.send(tutorial)
            # agenda apagar após 30 segundos
            self.tutorials[message.channel.id] = sent.id
            self.bot.loop.create_task(self._delete_after_delay(message.channel, sent.id, 30))

    async def _delete_after_delay(self, channel: discord.TextChannel, msg_id: int, seconds: int):
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=seconds))
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(RecruitmentCog(bot))
