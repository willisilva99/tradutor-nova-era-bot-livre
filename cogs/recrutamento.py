import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging

from db import SessionLocal, GuildConfig

# Configura logger
log = logging.getLogger("recrutamento")
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
log.addHandler(handler)

class RecrutamentoCog(commands.Cog):
    CHECK_EMOJI  = "✅"
    CROSS_EMOJI  = "❌"
    TUTORIAL_TTL = 30  # segundos

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Slash command para setar canal ---
    @app_commands.command(
        name="set_canal_recrutamento",
        description="Define o canal onde o bot processará recrutamento/procura de clã."
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
                f"✅ Canal de recrutamento definido para {canal.mention}.",
                ephemeral=True
            )
            log.info(f"Salvo canal {canal.id} para guild {guild_id}")
        except Exception:
            session.rollback()
            log.exception("Erro ao salvar canal de recrutamento")
            await interaction.followup.send("❌ Falha ao definir canal.", ephemeral=True)
        finally:
            session.close()

    # --- Listener on_message ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Sempre deixe o bot processar outros comandos
        await self.bot.process_commands(message)

        # DEBUG: veja TODAS as mensagens aqui
        log.debug(f"Mensagem em {message.channel} de {message.author}: {message.content!r}")

        # Ignora bots e DMs
        if message.author.bot or not message.guild:
            return

        # Pega config
        session = SessionLocal()
        cfg = session.query(GuildConfig).filter_by(guild_id=str(message.guild.id)).first()
        session.close()

        # Se não tiver canal configurado, ignora
        if not cfg or not cfg.recrutamento_channel_id:
            log.debug("→ Sem canal de recrutamento configurado")
            return

        # Se for outro canal, ignora
        if str(message.channel.id) != cfg.recrutamento_channel_id:
            log.debug(f"→ Canal {message.channel.id} ≠ configurado {cfg.recrutamento_channel_id}")
            return

        # Tenta dividir em 3 partes
        parts = [p.strip() for p in message.content.split(',')]
        is_valid = len(parts) == 3 and parts[2].lower() in ("recrutando", "procurando")

        if is_valid:
            nome_jogo, nome_clan, acao = parts
            log.debug("→ Formato válido, gerando embed")

            titulo = "Recrutamento de Clã" if acao.lower() == "recrutando" else "Procura de Clã"
            embed = discord.Embed(title=titulo, color=discord.Color.blue())
            embed.add_field(name="Jogador", value=message.author.mention, inline=False)
            embed.add_field(name="Nome no jogo", value=nome_jogo, inline=True)
            embed.add_field(name="Clã", value=nome_clan, inline=True)
            embed.add_field(name="Status", value=acao.capitalize(), inline=False)
            embed.set_footer(text="Reaja ✅ ou ❌ para entrar em contato.")

            # Apaga a mensagem original
            try:
                await message.delete()
            except:
                log.warning("Não consegui deletar a mensagem original")

            # Envia embed e adiciona as reações
            novo = await message.channel.send(embed=embed)
            await novo.add_reaction(self.CHECK_EMOJI)
            await novo.add_reaction(self.CROSS_EMOJI)
            return

        # Mensagem inválida: apaga e mostra tutorial
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
        msg = await message.channel.send(embed=tutorial)
        await asyncio.sleep(self.TUTORIAL_TTL)
        try:
            await msg.delete()
        except:
            pass

    async def cog_load(self):
        log.info("RecrutamentoCog carregado.")

async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutamentoCog(bot))
