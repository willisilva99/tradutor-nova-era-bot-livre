
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
LOG_CHANNEL_ID = 978460787586789406  # ID do canal de logs (opcional; se não quiser logs, deixe 0)
STAFF_ROLE_ID = 978464190979260426   # ID do cargo da staff (para mention no on_member_update, se quiser)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')  # [NomeJogo] - NomeDiscord

class NomeNoCanalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_for_name = set()  # IDs dos usuários aguardando resposta

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora bots e mensagens em DM
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        # Se o membro já estiver verificado, nada acontece
        if await self.is_verified(member):
            return

        # Apaga a mensagem original para evitar poluição
        try:
            await message.delete()
        except discord.Forbidden:
            await self.logar(f"[ERRO] Não pude apagar a msg de {member} em {channel.mention} (permissão negada).")

        # Se já estamos esperando esse membro, não repete o pedido
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)

        # Cria embed de verificação com termos (sem mencionar o formato exato)
        embed_pedido = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, você ainda não definiu seu **nome no jogo**.\n\n"
                "**Termos Básicos**:\n"
                "1. Ao prosseguir, você concorda com as regras do servidor.\n"
                "2. Se o nome fornecido **não** for realmente o que você usa no jogo, "
                "**poderá ser banido** tanto do servidor quanto do jogo.\n\n"
                f"Por favor, digite agora seu nome no jogo (você tem {WAIT_TIME} segundos)."
            ),
            color=COR_PADRAO
        )
        embed_pedido.set_footer(text="Sistema de Verificação")

        pedido_msg = await channel.send(embed=embed_pedido)

        # Aguarda a resposta do usuário no mesmo canal
        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(
                title="Tempo Esgotado",
                description=(
                    f"{member.mention}, você não respondeu em {WAIT_TIME} segundos.\n"
                    "Envie outra mensagem para tentar novamente."
                ),
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            # Apaga as mensagens de pedido e timeout após 30s
            await asyncio.sleep(30)
            try:
                await pedido_msg.delete()
                await timeout_msg.delete()
            except discord.Forbidden:
                pass
            return

        # Apaga a resposta do usuário para manter o canal limpo
        try:
            await resposta.delete()
        except discord.Forbidden:
            pass

        in_game_name = resposta.content.strip()
        # Usa o display_name para o apelido
        novo_nick = f"[{in_game_name}] - {member.display_name}"

        # Tenta editar o apelido do usuário
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            embed_perm = discord.Embed(
                title="Erro de Permissão",
                description=(
                    f"{member.mention}, não consigo alterar seu apelido.\n"
                    "Fale com um administrador!"
                ),
                color=COR_ERRO
            )
            perm_msg = await channel.send(embed=embed_perm)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(30)
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

        # Salva o apelido final no banco (novo_nick)
        self.salvar_in_game_name(member.id, novo_nick)

        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(
                f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\n"
                "Você está liberado para conversar!"
            ),
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} definiu seu apelido para '{novo_nick}' e foi verificado.")

        # Apaga as mensagens do embed de pedido e de sucesso após 30 segundos para não poluir
        await asyncio.sleep(30)
        try:
            await pedido_msg.delete()
            await final_msg.delete()
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        if after.id == after.guild.owner_id:
            return
        if before.nick == after.nick:
            return

        was_verified = (before.nick and NICK_REGEX.match(before.nick))
        is_still_verified = (after.nick and NICK_REGEX.match(after.nick))

        if was_verified and not is_still_verified:
            guild = after.guild
            system_channel = guild.system_channel
            embed_alerta = discord.Embed(
                title="Alerta de Nickname",
                description=(
                    f"{after.mention}, você removeu o prefixo do seu apelido.\n"
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role and system_channel:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")
            await self.logar(f"Usuário {after} removeu o prefixo. Nick era '{before.nick}' e virou '{after.nick}'.")

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
    await bot.add_cog(NomeNoCanalCog(bot))
