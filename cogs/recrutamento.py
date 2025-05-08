import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging

from db import SessionLocal, GuildConfig

log = logging.getLogger("recrutamento")
log.setLevel(logging.DEBUG)

class RecrutamentoCog(commands.Cog):
    CHECK_EMOJI  = "✅"
    CROSS_EMOJI  = "❌"
    TUTORIAL_TTL = 30  # segundos

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Slash para definir canal ---
    @app_commands.command(
        name="set_canal_recrutamento",
        description="Define o canal onde o bot processará recrutamento/procura"
    )
    @app_commands.describe(canal="Mencione o canal ou informe o ID dele")
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
            await interaction.followup.send(f"✅ Canal de recrutamento: {canal.mention}", ephemeral=True)
            log.info(f"Canal de recrutamento salvo: {canal.id} em guild {guild_id}")
        except Exception:
            log.exception("Erro ao salvar canal de recrutamento")
            await interaction.followup.send("❌ Falha ao definir canal.", ephemeral=True)
        finally:
            session.close()

    # --- Listener de mensagens ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Debug: veja NO CONSOLE TODOA mensagem chegando
        log.debug(f"on_message: #{message.channel} – {message.author}: {message.content!r}")

        # Ignora bots/DMs
        if message.author.bot or not message.guild:
            return

        # Busca config
        session = SessionLocal()
        cfg = session.query(GuildConfig).filter_by(guild_id=str(message.guild.id)).first()
        session.close()

        # Se não estiver no canal de recrutamento, ignora
        if not cfg or not cfg.recrutamento_channel_id:
            log.debug("→ Sem canal configurado, ignora")
            return
        if str(message.channel.id) != cfg.recrutamento_channel_id:
            log.debug(f"→ Canal {message.channel.id} != config {cfg.recrutamento_channel_id}")
            return

        # Formato válido?
        parts = [p.strip() for p in message.content.split(',')]
        if len(parts) == 3 and parts[2].lower() in ("recrutando", "procurando"):
            nome_jogo, nome_clan, acao = parts
            log.debug("→ Formato válido, gerando embed")
            titulo = "Recrutamento de Clã" if acao.lower()=="recrutando" else "Procura de Clã"
            embed = discord.Embed(title=titulo, color=discord.Color.blue())
            embed.add_field("Jogador", message.author.mention, inline=False)
            embed.add_field("Nome no jogo", nome_jogo, inline=True)
            embed.add_field("Clã", nome_clan, inline=True)
            embed.add_field("Status", acao.capitalize(), inline=False)
            embed.set_footer(text="Reaja ✅ ou ❌")

            try:
                await message.delete()
            except:
                log.warning("Não consegui deletar a mensagem original")
            novo = await message.channel.send(embed=embed)
            await novo.add_reaction(self.CHECK_EMOJI)
            await novo.add_reaction(self.CROSS_EMOJI)
            return

        # Mensagem inválida: limpa e mostra tutorial
        log.debug("→ Formato inválido, apagando e enviando tutorial")
        try:
            await message.delete()
        except:
            pass

        tutorial = discord.Embed(
            title="Como usar Recrutamento/Procura",
            description=(
                "`NomeJogador, NomeClã, recrutando`\n"
                "ou\n"
                "`NomeJogador, NomeClã, procurando`"
            ),
            color=discord.Color.gold()
        )
        tutorial_msg = await message.channel.send(embed=tutorial)
        await asyncio.sleep(self.TUTORIAL_TTL)
        try:
            await tutorial_msg.delete()
        except:
            pass

    async def cog_load(self):
        log.info("RecrutamentoCog carregado")

async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutamentoCog(bot))
