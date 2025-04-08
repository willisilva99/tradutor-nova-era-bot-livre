import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

from db import SessionLocal, PlayerName

########################################
# CONFIGURAÇÕES DE CORES (Padronização)
########################################
COR_PADRAO = discord.Color.from_rgb(255, 165, 0)   # Laranja
COR_SUCESSO = discord.Color.green()
COR_ERRO = discord.Color.red()
COR_ALERTA = discord.Color.yellow()

########################################
# OUTRAS CONFIGURAÇÕES
########################################
WAIT_TIME = 60           # Tempo (segundos) para esperar resposta do usuário
LOG_CHANNEL_ID = 978460787586789406  # ID do canal de logs (opcional)
STAFF_ROLE_ID = 978464190979260426   # ID do cargo da staff (para mention em alertas)
VERIFICADO_ROLE_ID = 978444009536094269  # ID do cargo que será dado ao jogador verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468  # ID do canal de verificação

# Essa regex é usada apenas para verificação interna (não exibida para o membro)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')  # Espera o formato: [NomeDoJogo] - NomeDiscord

class VerificacaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Guardará IDs dos membros que estão aguardando o fluxo de verificação/alteração
        self.waiting_for_name = set()

    # Este evento processa somente mensagens enviadas no canal de verificação
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Processa apenas mensagens no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        if message.author.bot:
            return  # Ignora mensagens de bots

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        # Se o membro já está verificado e envia alguma mensagem no canal de verificação,
        # apaga a mensagem para manter o canal limpo
        if await self.is_verified(member):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        content = message.content.strip().lower()

        # Se o membro enviar "mudar nick", inicia o fluxo de alteração de nick
        if content == "mudar nick":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            # Somente membros verificados podem alterar o nick pelo comando
            if not await self.is_verified(member):
                await channel.send(f"{member.mention}, você ainda não está verificado. Use o fluxo de verificação primeiro.")
                return
            await self.prompt_mudar_nick(member, channel)
            return

        # Se o membro não estiver verificado, este canal é dedicado à verificação.
        # Ou seja, qualquer mensagem válida será tratada como tentativa de verificação.
        # Se a mensagem não seguir o formato esperado, será apagada.
        # Espera-se que o formato seja: "Nome do Jogo, Nome do Discord"
        # ou "Nome do Jogo" (no qual, se não houver vírgula, o nome de Discord será o display_name atual).

        # Se já estamos esperando o membro, ignora mensagens adicionais
        if member.id in self.waiting_for_name:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        self.waiting_for_name.add(member.id)

        # Processar a mensagem recebida como tentativa de verificação
        parts = message.content.split(',')
        game_name = parts[0].strip()
        if not game_name:
            # Mensagem inválida; apaga e não processa
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            self.waiting_for_name.remove(member.id)
            return

        if len(parts) > 1 and parts[1].strip():
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        novo_nick = f"[{game_name}] - {discord_name}"

        # Tenta editar o apelido do usuário
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(f"{member.mention}, não consigo alterar seu apelido. Fale com um administrador!")
            self.waiting_for_name.remove(member.id)
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.remove(member.id)
            return

        # Salva o apelido final no banco
        self.salvar_in_game_name(member.id, novo_nick)

        # Atribui o cargo de verificado
        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir cargo ao {member}.")

        # Envia embed de sucesso (que será apagado posteriormente)
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\nVocê está verificado e liberado para conversar!",
            color=COR_SUCESSO
        )
        sucesso_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} verificou seu apelido para '{novo_nick}'.")

        # Aguarda 60 segundos e depois apaga a mensagem de sucesso (para manter o canal limpo)
        await asyncio.sleep(60)
        try:
            await sucesso_msg.delete()
        except discord.Forbidden:
            pass

    async def prompt_mudar_nick(self, member: discord.Member, channel: discord.TextChannel):
        """
        Fluxo para alterar o apelido quando o usuário digita "mudar nick" no canal de verificação.
        """
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)
        embed_mudar = discord.Embed(
            title="Alteração de Nickname",
            description=(
                f"{member.mention}, para alterar seu apelido, digite seu novo nome no jogo e, se quiser, seu novo nome no Discord "
                "separados por vírgula.\nExemplo: `NovoJogo, NovoNome`\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_mudar.set_footer(text="Sistema de Verificação - Mudar Nickname")
        mudar_msg = await channel.send(embed=embed_mudar)

        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="Tempo Esgotado",
                description=f"{member.mention}, você não respondeu a tempo. Tente novamente.",
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=timeout_embed)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            try:
                await mudar_msg.delete()
                await timeout_msg.delete()
            except discord.Forbidden:
                pass
            return

        try:
            await resposta.delete()
        except discord.Forbidden:
            pass

        parts = resposta.content.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(f"{member.mention}, não consegui alterar seu apelido. Fale com um administrador.")
            self.waiting_for_name.remove(member.id)
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.remove(member.id)
            return

        self.salvar_in_game_name(member.id, novo_nick)

        verificado_role = member.guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir cargo ao {member}.")
        
        embed_sucesso = discord.Embed(
            title="Alteração Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        sucesso_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")
        await asyncio.sleep(60)
        try:
            await mudar_msg.delete()
            await sucesso_msg.delete()
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Se o membro for um bot ou o dono, ignora
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
            # Remove cargo de verificado, se aplicável
            verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
            if verificado_role and verificado_role in after.roles:
                try:
                    await after.remove_roles(verificado_role)
                    await self.logar(f"Cargo removido de {after} por alteração de apelido inválido.")
                except discord.Forbidden:
                    await self.logar(f"[ERRO] Não consegui remover o cargo de {after}.")

    async def is_verified(self, member: discord.Member) -> bool:
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

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
