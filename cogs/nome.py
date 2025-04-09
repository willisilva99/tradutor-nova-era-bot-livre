import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
import datetime

from db import SessionLocal, PlayerName, GuildConfig

# Cores de exemplo
COR_SUCESSO = discord.Color.green()
COR_ERRO    = discord.Color.red()
COR_ALERTA  = discord.Color.yellow()

# Regex para apelidos: [Algo] - Algo
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def validar_nomes(game_name: str, discord_name: str) -> tuple[bool, str]:
    """
    Verifica se 'game_name' e 'discord_name' têm pelo menos 3 caracteres (ignorando espaços).
    Retorna (True, "") se estiver ok, senão (False, "mensagem de erro").
    """
    if len(game_name.replace(" ", "")) < 3:
        return False, "O nome do jogo deve ter pelo menos 3 caracteres."
    if len(discord_name.replace(" ", "")) < 3:
        return False, "O nome do Discord deve ter pelo menos 3 caracteres."
    return True, ""

class VerificacaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dicionário para contar quantas vezes cada user errou (user_id -> int)
        self.error_counts = {}

    # =======================================================
    #   1) Comandos Slash de Configuração do Servidor
    # =======================================================
    @app_commands.command(
        name="set_canal_verificacao",
        description="Define o canal de verificação para este servidor."
    )
    @app_commands.describe(canal="Mencione o canal ou informe o ID dele.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_canal_verificacao(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        session = SessionLocal()
        try:
            config = session.query(GuildConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = GuildConfig(guild_id=guild_id)
                session.add(config)

            config.verification_channel_id = str(canal.id)
            session.commit()

            await interaction.followup.send(
                f"Canal de verificação configurado para {canal.mention}.",
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(
                f"Erro ao configurar o canal: {e}",
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="set_canal_log",
        description="Define o canal de log para este servidor."
    )
    @app_commands.describe(canal="Mencione o canal ou informe o ID dele.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_canal_log(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        session = SessionLocal()
        try:
            config = session.query(GuildConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = GuildConfig(guild_id=guild_id)
                session.add(config)

            config.log_channel_id = str(canal.id)
            session.commit()

            await interaction.followup.send(
                f"Canal de log configurado para {canal.mention}.",
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(f"Erro ao configurar o canal de log: {e}", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(
        name="set_cargo_verificado",
        description="Define o cargo de verificado para este servidor."
    )
    @app_commands.describe(cargo="Mencione o cargo ou informe o ID dele.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_cargo_verificado(self, interaction: discord.Interaction, cargo: discord.Role):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        session = SessionLocal()
        try:
            config = session.query(GuildConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = GuildConfig(guild_id=guild_id)
                session.add(config)

            config.verificado_role_id = str(cargo.id)
            session.commit()

            await interaction.followup.send(
                f"Cargo de verificado configurado para {cargo.mention}",
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(f"Erro ao configurar o cargo: {e}", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(
        name="set_cargo_staff",
        description="Define o cargo de staff para este servidor."
    )
    @app_commands.describe(cargo="Mencione o cargo ou informe o ID dele.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_cargo_staff(self, interaction: discord.Interaction, cargo: discord.Role):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        session = SessionLocal()
        try:
            config = session.query(GuildConfig).filter_by(guild_id=guild_id).first()
            if not config:
                config = GuildConfig(guild_id=guild_id)
                session.add(config)

            config.staff_role_id = str(cargo.id)
            session.commit()

            await interaction.followup.send(
                f"Cargo de staff configurado para {cargo.mention}",
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(f"Erro ao configurar o cargo de staff: {e}", ephemeral=True)
        finally:
            session.close()

    # =======================================================
    #   2) Listener on_message: Fluxo de Verificação
    # =======================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar bots, DMs, etc.
        if message.author.bot or not message.guild:
            return

        # Verificar se há config para este servidor e se o canal é o correto
        config = self.get_guild_config(message.guild.id)
        if not config or not config.verification_channel_id:
            return

        # Se não estiver no canal configurado, sai
        if str(message.channel.id) != config.verification_channel_id:
            return

        member = message.author
        # Se o membro já estiver verificado, podemos apagar a msg ou ignorar
        if await self.is_verified(member, config):
            try:
                await message.delete()
            except:
                pass
            return

        # Tenta processar a mensagem como verificação:
        parts = message.content.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        # Valida
        ok, msg_erro = validar_nomes(game_name, discord_name)
        if not ok:
            # Caso de erro: incrementa contagem e exibe alerta
            await self.increment_and_handle_error(message, msg_erro)
            return

        # Monta o novo nick
        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await self.increment_and_handle_error(message, "O apelido excede 32 caracteres, tente encurtar.")
            return

        # Tenta editar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await self.increment_and_handle_error(
                message,
                "Não tenho permissão/hierarquia para alterar seu apelido."
            )
            return
        except Exception as e:
            await self.logar(
                message.guild,
                f"[ERRO] ao editar apelido de {member}: {e}",
                config
            )
            await self.increment_and_handle_error(message, "Ocorreu um erro ao alterar seu apelido.")
            return

        # Se chegou até aqui, deu certo: reseta contagem de erros
        self.reset_error_count(member.id)

        # Salvar no DB (PlayerName)
        session = SessionLocal()
        try:
            p = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            if not p:
                p = PlayerName(discord_id=str(member.id), in_game_name=novo_nick)
                session.add(p)
            else:
                p.in_game_name = novo_nick
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] {e}")
        finally:
            session.close()

        # Atribuir cargo verificado se existir
        if config.verificado_role_id:
            verificado_role = message.guild.get_role(int(config.verificado_role_id))
            if verificado_role:
                try:
                    await member.add_roles(verificado_role)
                except:
                    pass

        # Reagir com ✅
        try:
            await message.add_reaction("✅")
        except:
            pass

        # Enviar mensagem de sucesso
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(
                f"{member.mention}, seu apelido foi definido como: `{novo_nick}`.\n"
                "Você está verificado!"
            ),
            color=COR_SUCESSO
        )
        msg_sucesso = await message.channel.send(embed=embed_sucesso)

        # Log
        await self.logar(
            message.guild,
            f"O usuário {member} se verificou como '{novo_nick}'.",
            config
        )

        # [Opcional] Apagar a embed depois de X segundos
        await asyncio.sleep(15)
        try:
            await msg_sucesso.delete()
        except:
            pass

    # =======================================================
    #   3) Listener on_member_update (remover cargo se mudar)
    # =======================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Ignora bots e se não mudou nick
        if after.bot or before.nick == after.nick:
            return

        # Carrega config
        config = self.get_guild_config(after.guild.id)
        if not config:
            return

        was_verified = bool(before.nick and NICK_REGEX.match(before.nick))
        is_still_verified = bool(after.nick and NICK_REGEX.match(after.nick))

        if was_verified and not is_still_verified:
            # Remover cargo verificado
            if config.verificado_role_id:
                role = after.guild.get_role(int(config.verificado_role_id))
                if role and role in after.roles:
                    try:
                        await after.remove_roles(role)
                    except:
                        pass
            # Logar
            await self.logar(
                after.guild,
                f"{after} perdeu cargo verificado ao alterar o apelido fora do padrão.",
                config
            )

    # =======================================================
    #   4) Slash Command /mudar_nick
    # =======================================================
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            return

        config = self.get_guild_config(guild.id)
        if not config or not config.verification_channel_id:
            await interaction.followup.send(
                "Este servidor não está configurado para verificação.",
                ephemeral=True
            )
            return

        # Exigir que esteja no canal de verificação
        if str(interaction.channel_id) != config.verification_channel_id:
            await interaction.followup.send(
                "Este comando só pode ser usado no canal de verificação configurado.",
                ephemeral=True
            )
            return

        parts = dados.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            discord_name = interaction.user.display_name

        # Validação
        ok, erro_msg = validar_nomes(game_name, discord_name)
        if not ok:
            await interaction.followup.send(erro_msg, ephemeral=True)
            return

        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await interaction.followup.send(
                "O apelido excede 32 caracteres, tente encurtar.",
                ephemeral=True
            )
            return

        # Tentar editar
        try:
            await interaction.user.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.followup.send(
                "Não tenho permissão/hierarquia para alterar seu apelido.",
                ephemeral=True
            )
            return
        except Exception as e:
            await self.logar(guild, f"[ERRO] /mudar_nick: {e}", config)
            await interaction.followup.send("Erro ao alterar apelido. Tente mais tarde.", ephemeral=True)
            return

        # Salvar no DB
        session = SessionLocal()
        try:
            p = session.query(PlayerName).filter_by(discord_id=str(interaction.user.id)).first()
            if not p:
                p = PlayerName(discord_id=str(interaction.user.id), in_game_name=novo_nick)
                session.add(p)
            else:
                p.in_game_name = novo_nick
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] {e}")
        finally:
            session.close()

        # Adiciona cargo verificado
        if config.verificado_role_id:
            cargo_verif = guild.get_role(int(config.verificado_role_id))
            if cargo_verif and cargo_verif not in interaction.user.roles:
                try:
                    await interaction.user.add_roles(cargo_verif)
                except:
                    pass

        await interaction.followup.send(
            f"Seu apelido foi alterado para `{novo_nick}` com sucesso!",
            ephemeral=True
        )
        await self.logar(guild, f"{interaction.user} alterou apelido para '{novo_nick}'.", config)

    # =======================================================
    #   5) Funções Auxiliares
    # =======================================================
    def get_guild_config(self, guild_id: int) -> GuildConfig:
        """Obtém (ou None) as configs salvas no DB para este guild."""
        session = SessionLocal()
        try:
            return session.query(GuildConfig).filter_by(guild_id=str(guild_id)).first()
        finally:
            session.close()

    async def is_verified(self, member: discord.Member, config: GuildConfig) -> bool:
        """
        Checa se o membro tem cargo verificado E apelido no formato.
        Se quiser usar DB (PlayerName) também, pode.
        """
        if not config.verificado_role_id:
            return False
        role = member.guild.get_role(int(config.verificado_role_id))
        return bool(
            role in member.roles and
            member.nick and
            NICK_REGEX.match(member.nick)
        )

    async def apagar_e_alertar(self, message: discord.Message, texto_erro: str):
        """Apaga a mensagem original e envia uma embed de erro temporária."""
        embed = discord.Embed(
            title="Verificação Inválida",
            description=f"{message.author.mention}, {texto_erro}",
            color=COR_ERRO
        )
        msg_erro = await message.channel.send(embed=embed)

        # Apaga a mensagem do usuário
        try:
            await message.delete()
        except:
            pass

        # Apaga a mensagem de erro após alguns segundos
        await asyncio.sleep(10)
        try:
            await msg_erro.delete()
        except:
            pass

    def increment_error_count(self, user_id: int) -> int:
        """Incrementa o contador de erros de um usuário e retorna o novo total."""
        atual = self.error_counts.get(user_id, 0)
        atual += 1
        self.error_counts[user_id] = atual
        return atual

    def reset_error_count(self, user_id: int):
        """Reseta o contador de erros do usuário."""
        self.error_counts[user_id] = 0

    async def increment_and_handle_error(self, message: discord.Message, texto_erro: str):
        """
        Incrementa o erro do usuário. Se atingir 3, envia tutorial.
        Caso contrário, apenas faz o fluxo normal de apagar_e_alertar.
        """
        count = self.increment_error_count(message.author.id)
        await self.apagar_e_alertar(message, texto_erro)

        if count >= 3:
            # Envia tutorial e reseta contagem
            await self.enviar_tutorial(message.channel, message.author)
            self.reset_error_count(message.author.id)

    async def enviar_tutorial(self, channel: discord.TextChannel, member: discord.Member):
        """
        Envia uma mensagem de tutorial que some após 30 segundos.
        """
        embed = discord.Embed(
            title="Dica de Verificação",
            description=(
                f"{member.mention}, você errou 3 vezes a verificação.\n\n"
                "**Exemplo de uso**:\n"
                "Envie no chat: `MeuJogo, Fulano`\n\n"
                "Isso definirá seu nick como `[MeuJogo] - Fulano`.\n"
                "• Cada parte deve ter ao menos 3 caracteres.\n"
                "• Não ultrapasse 32 caracteres no total."
            ),
            color=COR_ALERTA
        )
        msg_tutorial = await channel.send(embed=embed)

        await asyncio.sleep(30)
        try:
            await msg_tutorial.delete()
        except:
            pass

    async def logar(self, guild: discord.Guild, texto: str, config: GuildConfig):
        """Envia logs no canal configurado, se houver um canal de log."""
        if not config or not config.log_channel_id:
            return
        canal = guild.get_channel(int(config.log_channel_id))
        if not canal:
            return
        data_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            await canal.send(f"[{data_str}] {texto}")
        except:
            pass

    # =======================================================
    #   6) ERRO PERSONALIZADO SE NÃO FOR ADMIN
    # =======================================================
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        """
        Se um usuário tentar usar comandos que exigem admin, 
        mostra nossa mensagem customizada em vez do "app não respondeu".
        """
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Somente Administrador pode executar este comando!",
                ephemeral=True
            )
        else:
            # Se for outro erro, pode levantar ou tratar de outra forma
            raise error

# Função OBRIGATÓRIA para carregar este cog
async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
