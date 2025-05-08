import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging

from db import SessionLocal, RecruitmentConfig, RecruitmentEntry

log = logging.getLogger("recrutamento")
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler())

class RecrutamentoCog(commands.Cog):
    CHECK_EMOJI  = "✅"
    CROSS_EMOJI  = "❌"
    TUTORIAL_TTL = 30  # segundos

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Slash: define canal de recrutamento
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
            cfg = session.query(RecruitmentConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                cfg = RecruitmentConfig(guild_id=guild_id, channel_id=str(canal.id))
                session.add(cfg)
            else:
                cfg.channel_id = str(canal.id)
            session.commit()
            await interaction.followup.send(
                f"✅ Canal de recrutamento definido para {canal.mention}.",
                ephemeral=True
            )
            log.info(f"[Recrutamento] Canal salvo: {canal.id} (guild {guild_id})")
        except Exception:
            session.rollback()
            log.exception("[Recrutamento] Erro ao salvar canal")
            await interaction.followup.send("❌ Falha ao definir canal.", ephemeral=True)
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.bot.process_commands(message)

        if message.author.bot or not message.guild:
            return

        # obtém o canal configurado
        session = SessionLocal()
        cfg = session.query(RecruitmentConfig).filter_by(guild_id=str(message.guild.id)).first()
        session.close()
        if not cfg or str(message.channel.id) != cfg.channel_id:
            return

        parts = [p.strip() for p in message.content.split(',')]
        if len(parts) == 3 and parts[2].lower() in ("recrutando", "procurando"):
            nome_jogo, nome_clan, acao = parts
            acao_lower = acao.lower()

            # monta embed
            titulo = "Recrutamento de Clã" if acao_lower == "recrutando" else "Procura de Clã"
            embed = discord.Embed(title=titulo, color=discord.Color.blue())
            embed.add_field("Jogador", message.author.mention, inline=False)
            embed.add_field("Nome no jogo", nome_jogo, inline=True)
            embed.add_field("Clã", nome_clan, inline=True)
            embed.add_field("Status", acao.capitalize(), inline=False)
            embed.set_footer(text="Reaja ✅ ou ❌ para entrar em contato.")

            try: await message.delete()
            except: pass

            novo = await message.channel.send(embed=embed)
            await novo.add_reaction(self.CHECK_EMOJI)
            await novo.add_reaction(self.CROSS_EMOJI)

            # salva no banco
            session = SessionLocal()
            try:
                entry = RecruitmentEntry(
                    guild_id=str(message.guild.id),
                    discord_user_id=str(message.author.id),
                    game_name=nome_jogo,
                    clan_name=nome_clan,
                    action=acao_lower
                )
                session.add(entry)
                session.commit()
                log.info(f"[Recrutamento] Entry salva: {entry.id}")
            except:
                session.rollback()
                log.exception("[Recrutamento] Erro ao salvar entry")
            finally:
                session.close()
            return

        # inválido: apaga e envia tutorial
        try: await message.delete()
        except: pass

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
        try: await msg.delete()
        except: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutamentoCog(bot))
