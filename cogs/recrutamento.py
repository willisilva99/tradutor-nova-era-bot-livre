import json
import os
import re
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta

CONFIG_PATH = "configs/recruitment_config.json"

class RecruitmentCog(commands.Cog):
    """Cog para gerenciar anúncios de recrutamento em canal configurado e filtrar mensagens."""

    def __init__(self, bot):
        self.bot = bot
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

        # Carrega canal de recrutamento por guild
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # Comando para definir canal de recrutamento
    @app_commands.command(name="set_recruit_channel", description="Define o canal de recrutamento.")
    @app_commands.describe(channel="Canal onde recrutamentos serão permitidos")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Você precisa da permissão Gerenciar Servidor.",
                ephemeral=True
            )

        self.config[str(interaction.guild.id)] = channel.id
        self.save_config()
        await interaction.response.send_message(
            f"✅ Canal de recrutamento definido: {channel.mention}",
            ephemeral=True
        )

    # Listener para filtrar mensagens
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignora mensagens de bots ou fora de guild
        if message.author.bot or message.guild is None:
            return

        guild_id = str(message.guild.id)
        channel_id = self.config.get(guild_id)
        if not channel_id or message.channel.id != channel_id:
            return

        # verifica se é recrutamento
        content = message.content.lower()
        if not re.search(r"\b(recrutando|buscando)\b", content, flags=re.IGNORECASE):
            try:
                await message.delete()
            except discord.Forbidden:
                return

            tutorial_msg = (
                "📢 **Como usar o canal de recrutamento**\n"
                "Use o comando `/recruit` para criar anúncios:\n"
                "• `/recruit recrutando <nome_clan> <descrição>` para oferecer vagas\n"
                "• `/recruit buscando <nome_clan> <descrição>` para procurar clã\n"
            )
            sent = await message.channel.send(embed=discord.Embed(
                title="Tutorial de Recrutamento",
                description=tutorial_msg,
                color=discord.Color.orange()
            ))
            # agenda apagar após 30 segundos
            asyncio.create_task(self._delete_after_delay(message.channel, sent.id, 30))

    async def _delete_after_delay(self, channel: discord.TextChannel, msg_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(RecruitmentCog(bot))
