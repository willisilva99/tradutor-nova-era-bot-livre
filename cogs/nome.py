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
COR_PADRAO   = discord.Color.from_rgb(255, 165, 0)   # Laranja
COR_SUCESSO  = discord.Color.green()
COR_ERRO     = discord.Color.red()
COR_ALERTA   = discord.Color.yellow()

########################################
# OUTRAS CONFIGURAÇÕES
########################################
WAIT_TIME = 60                                    # Tempo para esperar resposta (em segundos)
LOG_CHANNEL_ID = 978460787586789406               # ID do canal de logs (opcional)
STAFF_ROLE_ID = 978464190979260426                # ID do cargo da staff (para alertas)
VERIFICADO_ROLE_ID = 978444009536094269           # ID do cargo que será dado ao usuário verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468      # ID do canal de verificação

# Regex para o formato interno de apelido: [NomeDoJogo] - NomeDiscord
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def extrair_dados(input_str: str, member: discord.Member) -> tuple:
    """
    Extrai o nome do jogo e o nome do Discord a partir da mensagem do usuário.
    Se houver vírgula, o primeiro valor é o nome do jogo e o segundo é o novo nome
    do Discord; se não houver, usa o display_name do membro para o nome do Discord.
    
    Retorna uma tupla (game_name, discord_name).
    """
    parts = input_str.split(',')
    game_name = parts[0].strip()
    discord_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else member.display_name
    return game_name, discord_name

class VerificacaoCog(commands.Cog):
    """
    Cog responsável pelo fluxo de verificação e alteração de apelido.
    Os membros podem usar o canal de verificação para inserir seus dados;
    também há um comando de slash para alterar o nick.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_for_name = set()  # IDs dos usuários aguardando resposta

    # ---------------------------
    # Fluxo de verificação via canal dedicado
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Processa as mensagens enviadas no canal de verificação.
        Somente mensagens desse canal (VERIFICATION_CHANNEL_ID) serão tratadas.
        Se o membro não estiver verificado, considera a mensagem como tentativa
        de verificação (ou alteração via "mudar nick", que é processado separadamente).
        """
        # Processa apenas se a mensagem estiver no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        if message.author.bot:
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        content_lower = message.content.lower().strip()
        # Se a mensagem for "mudar nick", esse caso será tratado pelo comando de slash (ou através do prompt)
        if content_lower == "mudar nick":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if not await self.is_verified(member):
                await channel.send(f"{member.mention}, você ainda não está verificado. Use o fluxo de verificação primeiro.")
                return
            await self.prompt_mudar_nick(member, channel)
            return

        # Se o membro já está verificado, apaga qualquer mensagem enviada no canal de verificação
        if await self.is_verified(member):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Se o usuário ainda não está verificado, processa sua mensagem como tentativa de verificação.
        # Se já estiver aguardando resposta, apaga a mensagem extra.
        if member.id in self.waiting_for_name:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        self.waiting_for_name.add(member.id)

        # Cria embed de verificação com termos
        embed_pedido = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, para se verificar, por favor informe seu nome no jogo e, se desejar, seu novo nome no Discord, separados por vírgula.\n"
                "Exemplo: `Jão, Fulano`\n\n"
                "**Termos:** Se o nome informado não for realmente o que você usa no jogo, poderá ser banido do servidor e do jogo.\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_pedido.set_footer(text="Sistema de Verificação")
        pedido_msg = await channel.send(embed=embed_pedido)

        # Aguarda resposta do usuário
        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(
                title="Tempo Esgotado",
                description=(
                    f"{member.mention}, você não respondeu em {WAIT_TIME} segundos.\n"
                    "Envie 'mudar nick' para tentar novamente."
                ),
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            # Apaga os embeds após 60 segundos para manter o canal limpo
            await asyncio.sleep(60)
            try:
                await pedido_msg.delete()
                await timeout_msg.delete()
            except discord.Forbidden:
                pass
            return

        try:
            await resposta.delete()
        except discord.Forbidden:
            pass

        game_name, discord_name = extrair_dados(resposta.content, member)
        novo_nick = f"[{game_name}] - {discord_name}"

        # Tenta editar o apelido do usuário
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            embed_perm = discord.Embed(
                title="Erro de Permissão",
                description=(f"{member.mention}, não consigo alterar seu apelido.\nFale com um administrador!"),
                color=COR_ERRO
            )
            perm_msg = await channel.send(embed=embed_perm)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            try:
                await perm_msg.delete()
                await pedido_msg.delete()
            except discord.Forbidden:
                pass
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.remove(member.id)
            return

        # Salva o apelido final no DB
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribui o cargo de verificado
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir cargo ao {member}.")

        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\nVocê está liberado para conversar!"),
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} definiu seu apelido para '{novo_nick}' e foi verificado.")

        # Aguarda 60 segundos e depois apaga os embeds para manter o canal limpo
        await asyncio.sleep(60)
        try:
            await pedido_msg.delete()
            await final_msg.delete()
        except discord.Forbidden:
            pass

    # ---------------------------
    # Comando Slash para Alterar Nick
    # ---------------------------
    @app_commands.command(name="mudar_nick", description="Inicia o fluxo para alterar seu apelido.")
    async def mudar_nick(self, interaction: discord.Interaction):
        """Comando de Slash para que o usuário altere seu apelido."""
        member = interaction.user
        guild = member.guild
        channel = interaction.channel  # ou escolha um canal específico, se desejar

        # Verifica se o membro está verificado; só permite alteração se estiver
        if not await self.is_verified(member):
            await interaction.response.send_message(
                f"{member.mention}, você ainda não está verificado. Use o fluxo de verificação no canal designado.",
                ephemeral=True
            )
            return

        # Inicia o fluxo de alteração
        self.waiting_for_name.add(member.id)
        embed_mudar = discord.Embed(
            title="Alteração de Nickname",
            description=(
                f"{member.mention}, para alterar seu apelido, digite seu novo nome no jogo e, se desejar, "
                "seu novo nome no Discord, separados por vírgula.\n"
                "Exemplo: `NovoJogo, NovoNome`\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_mudar.set_footer(text="Sistema de Verificação - Mudar Nickname")
        await interaction.response.send_message(embed=embed_mudar, ephemeral=True)

        # Como o comando é slash, usamos wait_for para captar a resposta no canal
        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                f"{member.mention}, tempo esgotado. Tente novamente mais tarde.",
                ephemeral=True
            )
            self.waiting_for_name.remove(member.id)
            return

        try:
            await resposta.delete()
        except discord.Forbidden:
            pass

        game_name, discord_name = extrair_dados(resposta.content, member)
        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.followup.send(
                f"{member.mention}, não consegui alterar seu apelido. Fale com um administrador.",
                ephemeral=True
            )
            self.waiting_for_name.remove(member.id)
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.remove(member.id)
            return

        self.salvar_in_game_name(member.id, novo_nick)
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir cargo ao {member}.")

        embed_sucesso = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.followup.send(embed=embed_sucesso, ephemeral=True)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")

    # ---------------------------
    # on_member_update: Detecta alterações fora do padrão
    # ---------------------------
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
                    f"{after.mention}, você removeu parte do seu apelido verificado.\n"
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role and system_channel:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")
            await self.logar(f"Usuário {after} removeu parte do apelido. Nick era '{before.nick}' e virou '{after.nick}'.")

    # ---------------------------
    # Funções Auxiliares
    # ---------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        """Retorna True se o membro tiver apelido no padrão e registro no DB."""
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    def salvar_in_game_name(self, discord_id: int, nickname: str):
        """Insere ou atualiza o apelido no DB."""
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

    async def logar(self, mensagem: str):
        """Envia logs para o canal configurado."""
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
