# cogs/recrutamento.py

import json
import os
import re
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime

CONFIG_PATH = "configs/recruitment_config.json"
PATTERN = re.compile(
    r'^\s*(?P<name>.+?)\s*[\r\n]+'
    r'(?P<clan>.+?)\s*[\r\n]+'
    r'(?P<status>recrutando|procurando)\s*$',
    re.IGNORECASE
)

class RecruitmentCog(commands.Cog):
    """Cog para recrutar em canal configurado via slash."""

    def __init__(self, bot):
        self.bot = bot
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    @app_commands.command(name="set_recruit_channel", description="Define o canal de recrutamento.")
    @app_commands.describe(channel="Canal onde só poderá recrutar/buscar clã")
    async def set_recruit_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Você precisa da permissão **Gerenciar Servidor** para usar este comando.",
                ephemeral=True
            )

        self.config[str(interaction.guild_id)] = channel.id
        self.save_config()

        await interaction.response.send_message(
            f"✅ Canal de recrutamento definido: {channel.mention}",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        guild_id = str(message.guild.id)
        channel_id = self.config.get(guild_id)
        if message.channel.id != channel_id:
            return

        content = message.content.strip()
        match = PATTERN.match(content)

        if not match:
            # Mensagem inválida: apagar e mostrar tutorial
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            embed = discord.Embed(
                title="⚠️ Formato Inválido",
                description=(
                    "Envie **exatamente** 3 linhas:\n"
                    "① Nome completo\n"
                    "② Clã/Guilda\n"
                    "③ **recrutando** ou **procurando**\n\n"
                    "Exemplo:\n"
                    "`Will Doe`\n"
                    "`Anarquia Z`\n"
                    "`recrutando`"
                ),
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Tutorial de Recrutamento • Será apagado em 30s")

            tip = await message.channel.send(embed=embed)
            asyncio.create_task(self._delete_after(tip, 30))
            return

        # Formato correto: extrai dados
        name = match.group("name").strip()
        clan = match.group("clan").strip()
        status = match.group("status").lower()

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Monta o embed de recrutamento
        color = discord.Color.green() if status == "recrutando" else discord.Color.blue()
        embed = discord.Embed(
            title="📢 Anúncio de Recrutamento",
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url if message.author.avatar else None)
        embed.add_field(name="👤 Nome", value=f"{message.author.mention} — {name}", inline=False)
        embed.add_field(name="🏷️ Clã/Guilda", value=clan, inline=False)
        embed.add_field(
            name="📌 Status",
            value="🟢 Recrutando" if status == "recrutando" else "🔍 Procurando clã",
            inline=False
        )
        embed.set_footer(text="Reaja com ✅ ou ❌ para responder")

        post = await message.channel.send(embed=embed)
        await post.add_reaction("✅")
        await post.add_reaction("❌")

    async def _delete_after(self, message: discord.Message, delay: int):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(RecruitmentCog(bot))
