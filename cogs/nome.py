import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from discord import app_commands  # Para comandos slash

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
WAIT_TIME = 60  # Tempo (segundos) para esperar a entrada válida do usuário
LOG_CHANNEL_ID = 978460787586789406  # ID do canal de logs
STAFF_ROLE_ID = 978464190979260426   # ID do cargo da staff
VERIFICADO_ROLE_ID = 978444009536094269  # ID do cargo de verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468  # Canal de verificação

# Esta regex é usada para validar internamente se o nick está no padrão (para on_member_update)
# O padrão (não exibido) espera: [NomeDoJogo] - NomeDiscord
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def extrair_dados(input_str: str, member: discord.Member) -> tuple:
    """
    Extrai os dados do input do usuário.
    Se houver uma vírgula, o primeiro valor é o nome do jogo e o segundo é o nome do Discord.
    Se não houver, usa member.display_name para o nome do Discord.
    Retorna (game_name, discord_name)
    """
    parts = input_str.split(',')
    game = parts[0].strip()
    discord_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else member.display_name
    return game, discord_name

class VerificacaoCog(commands.Cog):
    """
    Cog que gerencia o fluxo de verificação e alteração de apelido
    no canal de verificação.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Armazena os IDs dos membros que estão aguardando entrada (para evitar processamento duplicado)
        self.waiting_for_name = {}
        # Armazena a quantidade de erros de cada membro (member.id => erro_count)
        self.error_counts = {}

    # -------------------------------------------------------------------
    # Fluxo Automático de Verificação no Canal de Verificação
    # -------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Processa apenas mensagens enviadas no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        # Se o membro já está verificado, não processa – mantém a mensagem enviada.
        if await self.is_verified(member):
            return

        # Se a mensagem for "mudar nick", deixa que o comando slash trate (não processa aqui)
        if message.content.lower().strip() == "mudar nick":
            return

        # Se o membro já estiver em fluxo, ignora mensagens extras (para evitar duplicidade)
        if member.id in self.waiting_for_name:
            return

        # Registra o timestamp dessa entrada para controle (se desejar)
        self.waiting_for_name[member.id] = asyncio.get_event_loop().time()

        # Processa a mensagem do usuário como tentativa de verificação
        game_name, discord_name = extrair_dados(message.content, member)

        # Se não houver nome do jogo, entrada inválida
        if not game_name:
            self.increment_error(member.id)
            error_embed = discord.Embed(
                title="Erro na Verificação",
                description=f"{member.mention}, o nome do jogo não pode estar vazio. Tente novamente.",
                color=COR_ERRO
            )
            error_msg = await channel.send(embed=error_embed)
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await asyncio.sleep(30)
            try:
                await error_msg.delete()
            except discord.Forbidden:
                pass
            self.waiting_for_name.pop(member.id, None)
            if self.error_counts.get(member.id, 0) >= 3:
                await self.enviar_instrucao(member, channel)
                self.error_counts[member.id] = 0
            return

        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            # Tenta alterar o apelido
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(f"{member.mention}, não tenho permissão para alterar seu apelido. Fale com um administrador.")
            self.waiting_for_name.pop(member.id, None)
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.pop(member.id, None)
            return

        # Salva o novo apelido no DB
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribui o cargo de verificado
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado para {member}.")

        # Adiciona uma reação "✅" na mensagem do usuário para indicar sucesso
        try:
            await message.add_reaction("✅")
        except discord.Forbidden:
            pass

        # Envia embed de sucesso (público)
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**. Você está verificado e liberado!",
            color=COR_SUCESSO
        )
        sucesso_msg = await channel.send(embed=embed_sucesso)
        await self.logar(f"O usuário {member} verificou seu apelido como '{novo_nick}'.")

        self.reset_error(member.id)
        self.waiting_for_name.pop(member.id, None)

        # Apaga o embed de sucesso após 30 segundos, mas mantém a mensagem do usuário
        await asyncio.sleep(30)
        try:
            await sucesso_msg.delete()
        except discord.Forbidden:
            pass

    # -------------------------------------------------------------------
    # Comando Slash para Alterar o Nick (para membros já verificados)
    # -------------------------------------------------------------------
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        member = interaction.user
        guild = member.guild
        channel = interaction.channel

        if channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message("Este comando só pode ser usado no canal de verificação.", ephemeral=True)
            return

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
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado para {member}.")

        embed_conf = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=embed_conf, ephemeral=True)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")

    # -------------------------------------------------------------------
    # Listener on_member_update: Se o nick verificado for alterado incorretamente
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
                description=f"{after.mention}, seu apelido saiu do formato verificado. Mantenha o formato ou poderá ser punido!",
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
    # Função auxiliar: Checa se o membro está verificado (apenas se tiver registro no DB)
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
    # Função auxiliar: Salva o apelido no DB
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
    # Função auxiliar: Incrementa contagem de erros para um membro
    # -------------------------------------------------------------------
    def increment_error(self, member_id: int):
        self.error_counts[member_id] = self.error_counts.get(member_id, 0) + 1

    # -------------------------------------------------------------------
    # Função auxiliar: Reseta contagem de erros para um membro
    # -------------------------------------------------------------------
    def reset_error(self, member_id: int):
        self.error_counts[member_id] = 0

    # -------------------------------------------------------------------
    # Se o membro errar 3 vezes, envia mensagem instrucional por 30 segundos
    # -------------------------------------------------------------------
    async def enviar_instrucao(self, member: discord.Member, channel: discord.TextChannel):
        instr_embed = discord.Embed(
            title="Dica para Verificação",
            description=(
                "Para se verificar corretamente, envie seu nome do jogo e, se quiser, seu nome do Discord, separados por vírgula.\n"
                "Exemplo: `Jão, Fulano`\n"
                "Se não quiser alterar seu nome no Discord, envie apenas o nome do jogo."
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
