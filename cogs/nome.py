import re
import time
import discord
from discord.ext import commands
import asyncio
import datetime
from discord import app_commands

from db import SessionLocal, PlayerName

########################################
# CONFIGURAÇÕES DE CORES
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

# Tempo de cooldown entre mensagens (para evitar spam)
COOLDOWN_SEGUNDOS = 5

# Regex para checar formato [Jogo] - Nome
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def validar_nomes(game_name: str, discord_name: str = "") -> tuple[bool, str]:
    """
    Verifica se 'game_name' e 'discord_name' atendem as regras mínimas.
    Retorna (True, "") se estiver tudo certo, ou (False, "mensagem_erro") se falhar.
    """
    # 1) Nome do jogo precisa ter >= 3 caracteres (ignorado espaços).
    if len(game_name.replace(" ", "")) < 3:
        return False, "O nome do jogo deve ter pelo menos 3 caracteres."

    # 2) Se o nome do Discord foi informado, checar >= 3 caracteres
    if discord_name:
        if len(discord_name.replace(" ", "")) < 3:
            return False, "O nome do Discord deve ter pelo menos 3 caracteres."
    return True, ""

class VerificacaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # 1) Para evitar processamento duplicado simultâneo
        self.waiting_for_name = {}
        # 2) Para contar erros de cada membro
        self.error_counts = {}
        # 3) Cooldown anti-spam (armazena timestamp da última mensagem do usuário)
        self.ultimo_envio = {}

    # ------------------------------------------------------------
    #                       LISTENER on_message
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Apenas no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        guild = member.guild
        channel = message.channel

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        # Se for "mudar nick" -> slash command /mudar_nick
        if message.content.lower().strip() == "mudar nick":
            return

        # -------------- 3) COOLDOWN ANTI-SPAM -----------------
        agora = time.time()
        if member.id in self.ultimo_envio:
            diferenca = agora - self.ultimo_envio[member.id]
            if diferenca < COOLDOWN_SEGUNDOS:
                # Muito rápido: apagar mensagem e ignorar
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                return
        # Atualiza a hora do último envio
        self.ultimo_envio[member.id] = agora

        # Se o membro já está verificado, apaga mensagem (canal só de verificação)
        if await self.is_verified(member):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Se o membro já estiver em fluxo, não processa de novo
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name[member.id] = asyncio.get_event_loop().time()

        # Extrair nomes
        parts = message.content.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        # 1) Validar nomes
        ok, msg_erro = validar_nomes(game_name, discord_name)
        if not ok:
            await self.tratar_erro_verificacao(member, channel, message, msg_erro)
            return

        # Montar novo nick e checar tamanho (4)
        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await self.tratar_erro_verificacao(
                member,
                channel,
                message,
                "O apelido final ultrapassa 32 caracteres, tente encurtar."
            )
            return

        # Tentar alterar e verificar (2) - Função genérica
        alterado = await self.alterar_apelido_e_verificar(member, novo_nick, channel)
        if not alterado:
            # Se falhar (Forbidden ou erro), sai
            self.waiting_for_name.pop(member.id, None)
            return

        # Adicionar reação de sucesso
        try:
            await message.add_reaction("✅")
        except discord.Forbidden:
            pass

        # Embed de sucesso
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**. Bem-vindo(a)!",
            color=COR_SUCESSO
        )
        msg_sucesso = await channel.send(embed=embed_sucesso)
        await self.logar(f"O usuário {member} se verificou como '{novo_nick}'.")

        self.reset_error(member.id)
        self.waiting_for_name.pop(member.id, None)

        # Apagar embed de sucesso após 30s
        await asyncio.sleep(30)
        try:
            await msg_sucesso.delete()
        except discord.Forbidden:
            pass

    # Função auxiliar para tratar erro na verificação
    async def tratar_erro_verificacao(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        message: discord.Message,
        msg_erro: str
    ):
        self.increment_error(member.id)
        error_embed = discord.Embed(
            title="Erro na Verificação",
            description=f"{member.mention}, {msg_erro}\nTente novamente.",
            color=COR_ERRO
        )
        error_msg = await channel.send(embed=error_embed)

        # Tenta apagar a mensagem do usuário
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Espera 15-30s e apaga a mensagem de erro
        await asyncio.sleep(15)
        try:
            await error_msg.delete()
        except discord.Forbidden:
            pass

        # Libera para outra tentativa
        self.waiting_for_name.pop(member.id, None)

        # Se excedeu 3 erros, manda instrução
        if self.error_counts.get(member.id, 0) >= 3:
            await self.enviar_instrucao(member, channel)
            self.error_counts[member.id] = 0

    # ------------------------------------------------------------
    #        (2) FUNÇÃO GENÉRICA p/ ALTERAR NICK & VERIFICAR
    # ------------------------------------------------------------
    async def alterar_apelido_e_verificar(
        self, member: discord.Member, novo_nick: str, channel: discord.TextChannel
    ) -> bool:
        """
        Tenta alterar o apelido do membro e atribuir cargo de verificado.
        Retorna True se deu certo, False se deu Forbidden ou erro inesperado.
        """
        # (5) Checar hierarquia/permissões:
        # Precisamos ver se o bot está acima do user. Exemplo simples:
        bot_member = member.guild.me  # Pega a Member do bot
        if bot_member.top_role.position <= member.top_role.position:
            # Se o cargo máximo do bot não estiver acima do cargo do membro
            await channel.send(
                f"{member.mention}, não consigo alterar seu apelido pois minha role está abaixo da sua. "
                "Peça a um administrador para ajustar a hierarquia."
            )
            return False

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(
                f"{member.mention}, não tenho permissão para alterar seu apelido. "
                "Fale com um administrador."
            )
            return False
        except Exception as e:
            await self.logar(f"[{self.timestamp()}][ERRO] ao editar apelido de {member}: {e}")
            return False

        # Salvar no DB
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribuir cargo verificado
        guild = member.guild
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(
                    f"[{self.timestamp()}][ERRO] Não pude atribuir cargo verificado para {member}."
                )

        return True

    # ------------------------------------------------------------
    #              COMANDO SLASH: /mudar_nick
    # ------------------------------------------------------------
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        member = interaction.user
        guild = member.guild
        channel = interaction.channel

        if channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no canal de verificação.",
                ephemeral=True
            )
            return

        # Checa se está verificado
        if not await self.is_verified(member):
            await interaction.response.send_message(
                "Você ainda não está verificado. Use o canal de verificação ou `/verify`.",
                ephemeral=True
            )
            return

        # Extrair nomes
        parts = dados.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        # Validar
        ok, msg_erro = validar_nomes(game_name, discord_name)
        if not ok:
            await interaction.response.send_message(msg_erro, ephemeral=True)
            return

        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await interaction.response.send_message(
                "O apelido final ultrapassa 32 caracteres, tente encurtar.",
                ephemeral=True
            )
            return

        # Alterar
        sucesso = await self.alterar_apelido_e_verificar(member, novo_nick, channel)
        if not sucesso:
            await interaction.response.send_message(
                "Não foi possível alterar seu apelido. Verifique minhas permissões/hierarquia.",
                ephemeral=True
            )
            return

        embed_conf = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=embed_conf, ephemeral=True)
        await self.logar(
            f"[{self.timestamp()}] O usuário {member} alterou seu apelido para '{novo_nick}'."
        )

    # ------------------------------------------------------------
    #                 on_member_update
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Ignora bots, dono do server e se não houve mudança de nick
        if after.bot or after.id == after.guild.owner_id:
            return
        if before.nick == after.nick:
            return

        # Se antes tinha nick verificado, mas agora não
        was_verified = bool(before.nick and NICK_REGEX.match(before.nick))
        is_still_verified = bool(after.nick and NICK_REGEX.match(after.nick))
        if was_verified and not is_still_verified:
            guild = after.guild
            system_channel = guild.system_channel

            embed_alerta = discord.Embed(
                title="Alerta de Nickname",
                description=(
                    f"{after.mention}, seu apelido saiu do formato verificado. "
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)

            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role and system_channel:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")
            
            # Remove cargo verificado
            verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
            if verificado_role and verificado_role in after.roles:
                try:
                    await after.remove_roles(verificado_role)
                    await self.logar(
                        f"[{self.timestamp()}] Cargo verificado removido de {after} (apelido inválido)."
                    )
                except discord.Forbidden:
                    await self.logar(
                        f"[{self.timestamp()}][ERRO] Não consegui remover cargo de {after}."
                    )

    # ------------------------------------------------------------
    #              COMANDO SLASH: /sincronizar_verificados
    # (9) Manter consistência no BD x Cargo de Verificado
    # ------------------------------------------------------------
    @app_commands.command(name="sincronizar_verificados", description="Sincroniza os membros verificados com o BD.")
    @app_commands.checks.has_role(STAFF_ROLE_ID)  # Exemplo: só staff pode usar
    async def sincronizar_verificados(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Pensando em um processo que pode levar um tempo

        guild = interaction.guild
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if not verificado_role:
            await interaction.followup.send("Cargo de verificado não encontrado.", ephemeral=True)
            return

        # 1) Coletar todos do BD
        session = SessionLocal()
        try:
            registros = session.query(PlayerName).all()
            # IDs no BD
            bd_ids = {r.discord_id for r in registros}
        finally:
            session.close()

        # 2) Coletar todos os membros que têm cargo verificado
        membros_com_role = [m for m in guild.members if verificado_role in m.roles]

        # 3) Ajustes: se o membro tem cargo verificado mas não consta no BD -> adiciona
        session = SessionLocal()
        contador_add = 0
        contador_remove = 0
        try:
            # Adicionar no BD quem não estiver lá
            for membro in membros_com_role:
                if str(membro.id) not in bd_ids:
                    # Salva no BD com o nick atual ou placeholder
                    novo_registro = PlayerName(
                        discord_id=str(membro.id),
                        in_game_name=membro.nick if membro.nick else membro.name
                    )
                    session.add(novo_registro)
                    contador_add += 1

            # Remover do BD quem não tem mais cargo (ou saiu do servidor)
            # - Filtrar somente quem não está no servidor ou não tem cargo
            membro_ids_no_servidor = {str(m.id) for m in guild.members}
            verificado_ids = {str(m.id) for m in membros_com_role}

            # Apagar do BD quem não está no servidor ou perdeu o cargo
            #   BD tem X, mas se X não estiver em verificado_ids -> remove
            registros = session.query(PlayerName).all()
            for reg in registros:
                if reg.discord_id not in verificado_ids:
                    session.delete(reg)
                    contador_remove += 1

            session.commit()
        except Exception as e:
            session.rollback()
            await self.logar(f"[{self.timestamp()}][ERRO] Sincronização BD: {e}")
        finally:
            session.close()

        msg = (
            f"Sincronização concluída!\n"
            f"Adicionados ao BD: {contador_add}\n"
            f"Removidos do BD: {contador_remove}"
        )
        await interaction.followup.send(msg, ephemeral=True)
        await self.logar(f"[{self.timestamp()}] {msg}")

    # ------------------------------------------------------------
    #  Verifica se o membro está verificado (Regex + BD)
    # ------------------------------------------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    # ------------------------------------------------------------
    #  Salva o apelido no DB
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    #  Funções auxiliares: log e contagem de erros
    # ------------------------------------------------------------
    async def logar(self, mensagem: str):
        """(8) Log com timestamp no canal de LOG."""
        if not LOG_CHANNEL_ID:
            return
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            try:
                await channel.send(mensagem)
            except discord.Forbidden:
                print(f"[ERRO] Permissão negada para enviar logs em {channel.id}.")

    def timestamp(self) -> str:
        """Retorna string de data/hora para logs."""
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return agora

    def increment_error(self, member_id: int):
        self.error_counts[member_id] = self.error_counts.get(member_id, 0) + 1

    def reset_error(self, member_id: int):
        self.error_counts[member_id] = 0

    async def enviar_instrucao(self, member: discord.Member, channel: discord.TextChannel):
        instr_embed = discord.Embed(
            title="Dica para Verificação",
            description=(
                "Para se verificar corretamente:\n"
                "• Envie seu nome do jogo e, se quiser, seu nome do Discord, separados por vírgula.\n"
                "Ex: `Jão, Fulano`\n"
                "• Cada parte deve ter pelo menos **3 caracteres**.\n"
                "• Seu apelido final não pode exceder **32 caracteres** no total.\n\n"
                "Se estiver com problemas, contate a staff."
            ),
            color=COR_PADRAO
        )
        msg_instr = await channel.send(embed=instr_embed)
        await asyncio.sleep(15)
        try:
            await msg_instr.delete()
        except discord.Forbidden:
            pass

# ------------------------------------------------------------
# SETUP DO COG
# ------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
