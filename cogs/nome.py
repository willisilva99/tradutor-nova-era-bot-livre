import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from discord import app_commands  # Para comandos de slash

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
WAIT_TIME = 60  # Tempo de espera (em segundos) para o usuário responder
LOG_CHANNEL_ID = 978460787586789406  # Canal de logs
STAFF_ROLE_ID = 978464190979260426   # Cargo da staff
VERIFICADO_ROLE_ID = 978444009536094269  # Cargo que será atribuído ao membro verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468  # Canal de verificação

# Regex para validar internamente o formato de apelido (para on_member_update, etc.)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def extrair_dados(input_str: str, member: discord.Member) -> tuple:
    """
    Extrai o nome do jogo e o nome do Discord do input.
    Se houver vírgula, o primeiro valor é o nome do jogo e o segundo é o nome do Discord;
    caso contrário, usa member.display_name.
    Retorna (game_name, discord_name)
    """
    parts = input_str.split(',')
    game = parts[0].strip()
    discord_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else member.display_name
    return game, discord_name

class VerificacaoCog(commands.Cog):
    """
    Cog que gerencia o fluxo de verificação e alteração de apelido
    exclusivamente no canal de verificação.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Armazena IDs dos membros que estão aguardando resposta
        self.waiting_for_name = {}
        # Armazena a contagem de erros de cada membro
        self.error_counts = {}

    # -------------------------------------------------------------------
    # Fluxo Automático de Verificação no canal designado
    # -------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Processa somente mensagens enviadas no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        if message.author.bot:
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignore o dono do servidor
        if member.id == guild.owner_id:
            return

        # Se o membro já estiver verificado, apaga a mensagem para manter o canal limpo
        if await self.is_verified(member):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Se a mensagem for um comando de alteração (“mudar nick”), deixamos para o comando de slash.
        if message.content.lower().strip() == "mudar nick":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Verifica se o membro já está em fluxo; se sim, apaga mensagens extras
        if member.id in self.waiting_for_name:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Inicia fluxo e registra timestamp (caso queira tratar mensagens duplicadas)
        self.waiting_for_name[member.id] = asyncio.get_event_loop().time()

        # Não apaga a mensagem válida enviada – pois queremos manter ela no canal se estiver correta.
        # Processa os dados da mensagem do usuário
        game_name, discord_name = extrair_dados(message.content, member)
        if not game_name:
            # Se o nome do jogo estiver vazio, trata como erro
            self.increment_error(member.id)
            error_embed = discord.Embed(
                title="Erro na Verificação",
                description=(f"{member.mention}, você deve informar o nome do jogo. Tente novamente."),
                color=COR_ERRO
            )
            error_msg = await channel.send(embed=error_embed)
            await asyncio.sleep(30)
            try:
                await error_msg.delete()
            except discord.Forbidden:
                pass
            del self.waiting_for_name[member.id]
            if self.error_counts.get(member.id, 0) >= 3:
                await self.enviar_instrucao(member, channel)
                self.error_counts[member.id] = 0
            return

        novo_nick = f"[{game_name}] - {discord_name}"

        # Tenta alterar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            error_perm = await channel.send(f"{member.mention}, não consigo alterar seu apelido. Fale com um administrador.")
            del self.waiting_for_name[member.id]
            await asyncio.sleep(30)
            try:
                await error_perm.delete()
            except discord.Forbidden:
                pass
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            del self.waiting_for_name[member.id]
            return

        # Adiciona uma reação de confirmação à mensagem do usuário
        try:
            await message.add_reaction("✅")
        except discord.Forbidden:
            pass

        # Salva o apelido final no DB
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribui o cargo de verificado
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado para {member}.")

        # Envia embed de sucesso (que ficará 30 segundos e depois será apagado)
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.\nVocê está liberado para conversar!"),
            color=COR_SUCESSO
        )
        sucesso_msg = await channel.send(embed=embed_sucesso)
        await self.logar(f"O usuário {member} verificou seu apelido como '{novo_nick}'.")

        # Remove o membro do fluxo e reinicia contador de erro
        if member.id in self.waiting_for_name:
            del self.waiting_for_name[member.id]
        self.reset_error(member.id)

        # Apaga o embed de sucesso após 30 segundos (mantendo a mensagem do usuário intacta)
        await asyncio.sleep(30)
        try:
            await sucesso_msg.delete()
        except discord.Forbidden:
            pass

    # -------------------------------------------------------------------
    # Comando Slash para alterar Nick (para membros já verificados)
    # -------------------------------------------------------------------
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        member = interaction.user
        guild = member.guild
        channel = interaction.channel

        # Verifica se o comando foi usado no canal de verificação
        if channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message("Este comando só pode ser usado no canal de verificação.", ephemeral=True)
            return

        # Apenas membros verificados podem usar este comando
        if not await self.is_verified(member):
            await interaction.response.send_message("Você ainda não está verificado. Use /verify para se verificar.", ephemeral=True)
            return

        game_name, discord_name = extrair_dados(dados, member)
        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para alterar seu apelido. Fale com um administrador.", ephemeral=True)
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
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado a {member}.")

        embed_conf = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=embed_conf, ephemeral=True)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")

    # -------------------------------------------------------------------
    # Listener on_member_update: Se o nick for alterado para um formato inválido
    # -------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or after.id == after.guild.owner_id:
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
                    f"{after.mention}, seu apelido saiu do formato verificado.\n"
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role and system_channel:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")
            verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
            if verificado_role and verificado_role in after.roles:
                try:
                    await after.remove_roles(verificado_role)
                    await self.logar(f"Cargo removido de {after} por alteração inválida de apelido.")
                except discord.Forbidden:
                    await self.logar(f"[ERRO] Não consegui remover o cargo de {after}.")

    # -------------------------------------------------------------------
    # Função auxiliar: checa se o membro está verificado
    # -------------------------------------------------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    # -------------------------------------------------------------------
    # Função auxiliar: salva o apelido no DB
    # -------------------------------------------------------------------
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

    # -------------------------------------------------------------------
    # Função auxiliar: Log de Ações
    # -------------------------------------------------------------------
    async def logar(self, mensagem: str):
        if not LOG_CHANNEL_ID:
            return
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            try:
                await channel.send(mensagem)
            except discord.Forbidden:
                print("[ERRO] Permissão negada para enviar logs no canal de log.")

    # -------------------------------------------------------------------
    # Função auxiliar: Incrementa erro para um membro
    # -------------------------------------------------------------------
    def increment_error(self, member_id: int):
        self.error_counts[member_id] = self.error_counts.get(member_id, 0) + 1

    # -------------------------------------------------------------------
    # Função auxiliar: Reseta erro para um membro
    # -------------------------------------------------------------------
    def reset_error(self, member_id: int):
        if member_id in self.error_counts:
            self.error_counts[member_id] = 0

    # -------------------------------------------------------------------
    # Se o usuário errar 3 vezes, envia uma instrução adicional por 30 segundos
    # -------------------------------------------------------------------
    async def enviar_instrucao(self, member: discord.Member, channel: discord.TextChannel):
        instr_embed = discord.Embed(
            title="Dica para Verificação",
            description=(
                "Para se verificar corretamente, envie seu nome no jogo e, se desejar, seu nome no Discord,\n"
                "separados por uma vírgula.\n"
                "Exemplo: `Jão, Fulano`\n"
                "Se você não quiser alterar seu nome no Discord, envie apenas o nome do jogo."
            ),
            color=COR_PADRAO
        )
        instr_msg = await channel.send(embed=instr_embed)
        await asyncio.sleep(30)
        try:
            await instr_msg.delete()
        except discord.Forbidden:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
