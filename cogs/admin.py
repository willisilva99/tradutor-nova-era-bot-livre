import discord
from discord import app_commands
from discord.ext import commands

class AdminCog(commands.Cog):
    """Cog para comandos administrativos (ex: /clear)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="clear",
        description="Limpa mensagens do chat (máx: 3000)."
    )
    @app_commands.describe(amount="Quantidade de mensagens a deletar (1-3000)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        """
        Deleta uma quantidade específica de mensagens no canal.
        Exemplo de uso: /clear amount:10
        """
        if amount < 1 or amount > 3000:
            # Retorna uma mensagem ephemeral para o usuário
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="⚠️ **Escolha um número entre 1 e 3000.**",
                    color=discord.Color.yellow()
                ),
                ephemeral=True
            )
            return

        # Defer para mostrar que estamos "pensando" (carregando)
        await interaction.response.defer(thinking=True)

        # Apaga as mensagens
        deleted = await interaction.channel.purge(limit=amount)

        # Envia feedback (ephemeral = True)
        embed = discord.Embed(
            title="🧹 Limpeza",
            description=f"{len(deleted)} mensagens apagadas!",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error):
        """Trata erros do comando /clear."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ **Você não tem permissão para apagar mensagens!**",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ **Erro:** {error}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

async def setup(bot):
    """Função especial que o Discord.py usa para carregar a cog."""
    await bot.add_cog(AdminCog(bot))
