import discord
from discord.ext import commands
from discord import app_commands
import asyncio

from db import SessionLocal, GuildConfig

class RecrutamentoCog(commands.Cog):
    """
    Cog para processar recrutamento e procura de clã.
    - Comando /set_canal_recrutamento para definir o canal
    - Mensagens no formato:
        NomeJogador, NomeClã, recrutando
        NomeJogador, NomeClã, procurando
      geram embeds com reações ✅ e ❌.
    - Qualquer outra mensagem no canal é apagada e exibe tutorial por 30s.
    """

    CHECK_EMOJI = "✅"
    CROSS_EMOJI = "❌"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ================================
    # Slash command para configurar canal
    # ================================
    @app_commands.command(
        name="set_canal_recrutamento",
        description="Define o canal onde o bot processará recrutamento e procura de clã."
    )
    @app_commands.describe(canal="Mencione o canal ou informe o ID dele.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_canal_recrutamento(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        session = SessionLocal()
        try:
            cfg = session.query(GuildConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                cfg = GuildConfig(guild_id=guild_id)
                session.add(cfg)
            cfg.recrutamento_channel_id = str(canal.id)
            session.commit()
            await interaction.followup.send(
                f"Canal de recrutamento definido para {canal.mention}.",
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(f"Erro ao definir canal: {e}", ephemeral=True)
        finally:
            session.close()

    # ================================
    # Listener on_message
    # ================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora bots, DMs, servidores sem config
        if message.author.bot or not message.guild:
            return

        session = SessionLocal()
        cfg = session.query(GuildConfig).filter_by(guild_id=str(message.guild.id)).first()
        session.close()
        # Se canal não configurado ou mensagem em outro canal, ignora
        if not cfg or not cfg.recrutamento_channel_id:
            return
        if str(message.channel.id) != cfg.recrutamento_channel_id:
            return

        content = message.content.strip()
        parts = [p.strip() for p in content.split(',')]

        # Caso formato válido: gera embed
        if len(parts) == 3 and parts[2].lower() in ("recrutando", "procurando"):
            nome_jogo, nome_clan, acao = parts
            acao_lower = acao.lower()

            titulo = "Recrutamento de Clã" if acao_lower == "recrutando" else "Procura de Clã"
            embed = discord.Embed(title=titulo, color=discord.Color.blue())
            embed.add_field(name="Jogador (Discord)", value=message.author.mention, inline=False)
            embed.add_field(name="Nome no jogo",     value=nome_jogo,          inline=True)
            embed.add_field(name="Clã",              value=nome_clan,          inline=True)
            embed.add_field(name="Status",           value=acao.capitalize(),  inline=False)
            embed.set_footer(text="Reaja ✅ ou ❌ para entrar em contato.")

            # Apaga mensagem original
            try:
                await message.delete()
            except:
                pass

            # Envia embed e adiciona reações
            novo_msg = await message.channel.send(embed=embed)
            await novo_msg.add_reaction(self.CHECK_EMOJI)
            await novo_msg.add_reaction(self.CROSS_EMOJI)
            return

        # Qualquer outra mensagem: apagar e enviar tutorial
        try:
            await message.delete()
        except:
            pass

        tutorial = discord.Embed(
            title="Como usar Recrutamento/Procura de Clã",
            description=(
                "Envie uma mensagem neste formato:\n\n"
                "`NomeJogador, NomeClã, recrutando`\n"
                "ou\n"
                "`NomeJogador, NomeClã, procurando`\n\n"
                "Exemplo:\n"
                "`Fulano123, OrdemDosHeróis, recrutando`"
            ),
            color=discord.Color.gold()
        )
        tutorial_msg = await message.channel.send(embed=tutorial)

        # Desaparece após 30s
        await asyncio.sleep(30)
        try:
            await tutorial_msg.delete()
        except:
            pass

    async def cog_load(self):
        print(f"{self.__class__.__name__} carregado.")

async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutamentoCog(bot))
