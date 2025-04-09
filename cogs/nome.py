import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from discord import app_commands  # para comandos de slash

from db import SessionLocal, PlayerName

########################################
# CONFIGURAÇÕES DE CORES (Padronização)
########################################
COR_PADRAO   = discord.Color.from_rgb(255, 165, 0)  # Laranja
COR_SUCESSO  = discord.Color.green()
COR_ERRO     = discord.Color.red()
COR_ALERTA   = discord.Color.yellow()

########################################
# OUTRAS CONFIGURAÇÕES
########################################
WAIT_TIME = 60  # Tempo para esperar resposta (em segundos)
LOG_CHANNEL_ID = 978460787586789406  # ID do canal de logs
STAFF_ROLE_ID = 978464190979260426   # ID do cargo da staff
VERIFICADO_ROLE_ID = 978444009536094269  # ID do cargo que será dado ao usuário verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468  # ID do canal de verificação

# Regex para validar o formato interno (não exibido ao usuário)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def extrair_dados(input_str: str, member: discord.Member) -> tuple:
    """
    Extrai, a partir da string fornecida, duas partes:
      - game: o nome do jogo,
      - discord_name: o nome de exibição desejado para o Discord.
    Se não houver separador (vírgula), usa o display_name do membro.
    """
    parts = input_str.split(',')
    game = parts[0].strip()
    discord_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else member.display_name
    return game, discord_name

class VerificacaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================================================================
    # Comando Slash para iniciar o fluxo de verificação (ou alteração de nick)
    # =========================================================================
    @app_commands.command(name="verify", description="Inicia o fluxo de verificação ou alteração do seu nick.")
    async def verify(self, interaction: discord.Interaction, dados: str):
        """
        O membro deve usar este comando no canal de verificação para definir seu apelido.
        Parâmetro 'dados': informe o nome do jogo e, opcionalmente, o nome do Discord separados por vírgula.
        Exemplo: Jão, Fulano
        Se o segundo valor não for informado, será usado o display_name atual.
        """
        member = interaction.user
        guild = member.guild

        # Verifica se o comando foi usado no canal de verificação
        if interaction.channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no canal de verificação.",
                ephemeral=True
            )
            return

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            await interaction.response.send_message("O dono do servidor não precisa usar este comando.", ephemeral=True)
            return

        # Extrai os dados fornecidos
        game_name, discord_name = extrair_dados(dados, member)
        novo_nick = f"[{game_name}] - {discord_name}"

        # Tenta alterar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar seu apelido. Fale com um administrador.",
                ephemeral=True
            )
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            await interaction.response.send_message("Erro inesperado. Tente novamente mais tarde.", ephemeral=True)
            return

        # Salva no DB
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribui o cargo de verificado, se disponível
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Permissão negada ao tentar dar cargo para {member}.")

        # Envia a mensagem de confirmação (pública)
        embed_conf = discord.Embed(
            title="Verificação Concluída",
            description=f"✅ {member.mention}, seu apelido foi definido para **`{novo_nick}`**.\nVocê está liberado para conversar!",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=embed_conf)

        await self.logar(f"O usuário {member} verificou seu apelido como '{novo_nick}'.")

    # =========================================================================
    # Comando Slash para alterar o nick (caso já esteja verificado)
    # =========================================================================
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        """
        Permite que um membro já verificado altere seu apelido usando a mesma lógica.
        Parâmetro 'dados': informe o novo nome do jogo e, opcionalmente, o novo nome do Discord.
        """
        member = interaction.user
        guild = member.guild

        if interaction.channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no canal de verificação.",
                ephemeral=True
            )
            return

        if not await self.is_verified(member):
            await interaction.response.send_message(
                "Você ainda não está verificado. Use o comando /verify para se verificar.",
                ephemeral=True
            )
            return

        game_name, discord_name = extrair_dados(dados, member)
        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar seu apelido. Fale com um administrador.",
                ephemeral=True
            )
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            await interaction.response.send_message("Erro inesperado. Tente novamente mais tarde.", ephemeral=True)
            return

        self.salvar_in_game_name(member.id, novo_nick)

        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Permissão negada ao tentar dar cargo para {member}.")

        embed_conf = discord.Embed(
            title="Alteração Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=embed_conf)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")

    # =========================================================================
    # Listener on_member_update: remove verificado se o nick não seguir o padrão
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        if after.id == after.guild.owner_id:
            return
        if before.nick == after.nick:
            return
        was_verified = before.nick and NICK_REGEX.match(before.nick)
        is_still_verified = after.nick and NICK_REGEX.match(after.nick)
        if was_verified and not is_still_verified:
            guild = after.guild
            system_channel = guild.system_channel
            embed_alerta = discord.Embed(
                title="Alerta de Nickname",
                description=(
                    f"{after.mention}, você alterou seu apelido para um formato inválido.\n"
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role and system_channel:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")
            # Remove o cargo de verificado, se aplicável
            verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
            if verificado_role and verificado_role in after.roles:
                try:
                    await after.remove_roles(verificado_role)
                    await self.logar(f"Cargo removido de {after} por alteração inválida de apelido.")
                except discord.Forbidden:
                    await self.logar(f"[ERRO] Não consegui remover o cargo de {after}.")

    # =========================================================================
    # Função auxiliar: checar se o membro está verificado
    # =========================================================================
    async def is_verified(self, member: discord.Member) -> bool:
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    # =========================================================================
    # Função auxiliar: salvar o apelido no DB
    # =========================================================================
    def salvar_in_game_name(self, discord_id: int, nickname: str):
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(discord_id)).first()
            if reg:
                reg.in_game_name = nickname
            else:
                novo = PlayerName(discord_id=str(discord_id), in_game_name=nickname)
                session.add(novo)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] Não foi possível salvar: {e}")
        finally:
            session.close()

    # =========================================================================
    # Função auxiliar: log de ações
    # =========================================================================
    async def logar(self, mensagem: str):
        if not LOG_CHANNEL_ID:
            return
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            try:
                await channel.send(mensagem)
            except discord.Forbidden:
                print("[ERRO] Permissão negada para enviar logs no canal de log.")

async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
