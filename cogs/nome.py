import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

from db import SessionLocal, PlayerName

########################################
# CONFIGURAÇÕES DE CORES (Padronização)
########################################
COR_PADRAO = discord.Color.from_rgb(255, 165, 0)   # Laranja (por exemplo)
COR_SUCESSO = discord.Color.green()
COR_ERRO = discord.Color.red()
COR_ALERTA = discord.Color.yellow()

########################################
# OUTRAS CONFIGURAÇÕES
########################################
WAIT_TIME = 60           # Tempo (segundos) para esperar resposta do usuário
LOG_CHANNEL_ID = 123456  # ID do canal de logs (opcional; se não quiser logs, deixe 0)
STAFF_ROLE_ID = 654321   # ID do cargo da staff (para mention no on_member_update, se quiser)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')  # [NomeJogo] - NomeDiscord

class NomeNoCanalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_for_name = set()  # Usuários que estão no "processo" de enviar nome

    # -----------------------------------------------------
    # 1) Interceptar mensagens de quem não está verificado
    # -----------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel

        # Se já verificado, libera
        if await self.is_verified(member):
            return

        # Apaga a mensagem
        try:
            await message.delete()
        except discord.Forbidden:
            await self.logar(f"[ERRO] Não pude apagar a msg de {member} em {channel.mention} por falta de permissão.")

        # Se já estamos esperando esse membro, não repete a pergunta
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)

        # Cria Embed de Termos/Pedido
        embed_pedido = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, você ainda não definiu seu **nome no jogo**.\n\n"
                "**Termos Básicos**:\n"
                "1. Seu apelido deve ficar no formato `[NomeDoJogo] - NomeDiscord`.\n"
                "2. Ao prosseguir, você concorda com as regras do servidor.\n"
                "3. Se o nome fornecido **não** for realmente o que você usa no jogo, "
                "**poderá ser banido** tanto do servidor quanto do jogo.\n\n"
                f"Por favor, digite agora seu nome no jogo (você tem {WAIT_TIME} segundos)."
            ),
            color=COR_PADRAO
        )
        embed_pedido.set_footer(text="Sistema de Verificação")

        await channel.send(embed=embed_pedido)

        # Espera resposta
        def check(m: discord.Message):
            return (m.author.id == member.id) and (m.channel.id == channel.id)

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
            await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            return

        # Usuário mandou o nome do jogo
        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        # Tentar editar apelido
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
            await channel.send(embed=embed_perm)
            self.waiting_for_name.remove(member.id)
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            self.waiting_for_name.remove(member.id)
            return

        # Salvar no DB
        self.salvar_in_game_name(member.id, in_game_name)

        # Embed de sucesso
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(
                f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\n"
                "Você está liberado para conversar!"
            ),
            color=COR_SUCESSO
        )
        await channel.send(embed=embed_sucesso)

        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} definiu nome no jogo: '{in_game_name}' e foi verificado.")

    # -----------------------------------------------------
    # 2) on_member_update: se removeu prefixo, alerta staff
    # -----------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot or after.bot:
            return
        if before.nick == after.nick:
            return

        was_verified = (before.nick and NICK_REGEX.match(before.nick))
        is_still_verified = (after.nick and NICK_REGEX.match(after.nick))

        if was_verified and not is_still_verified:
            # Alerta no system_channel ou logs
            guild = after.guild
            system_channel = guild.system_channel
            embed_alerta = discord.Embed(
                title="Alerta de Nickname",
                description=(
                    f"{after.mention}, você removeu o prefixo `[NomeDoJogo] - ...` do seu apelido.\n"
                    "Mantenha o formato ou poderá ser punido!"
                ),
                color=COR_ALERTA
            )
            if system_channel:
                await system_channel.send(embed=embed_alerta)

            # Mencionar staff, se quiser
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role:
                await system_channel.send(f"{staff_role.mention}, fiquem de olho.")

            # Se quiser banir ou reverter
            # try:
            #     await after.edit(nick=before.nick)
            # except discord.Forbidden:
            #     pass

            await self.logar(f"Usuário {after} removeu prefixo. Nick era '{before.nick}' e virou '{after.nick}'.")

    # -----------------------------------------------------
    # 3) Checar se usuário está verificado
    # -----------------------------------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        """
        Está verificado se:
          1. Nick no formato [NomeJogo] - NomeDiscord
          2. Registro no DB
        """
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False

        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    # -----------------------------------------------------
    # 4) Salvar no DB (com data/hora)
    # -----------------------------------------------------
    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(discord_id)).first()
            if reg:
                reg.in_game_name = in_game_name
                # updated_at é automático se no db.py estiver `onupdate=datetime.utcnow`
            else:
                # registramos data/hora pela 1ª vez
                novo = PlayerName(discord_id=str(discord_id), in_game_name=in_game_name)
                session.add(novo)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] Não foi possível salvar: {e}")
        finally:
            session.close()

    # -----------------------------------------------------
    # 5) Log de Ações (Opcional)
    # -----------------------------------------------------
    async def logar(self, mensagem: str):
        """
        Envia logs para LOG_CHANNEL_ID, se configurado.
        """
        if not LOG_CHANNEL_ID:
            return  # Se não definiu, não faz nada
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            try:
                await channel.send(mensagem)
            except discord.Forbidden:
                print("[ERRO] Permissão negada para enviar logs no canal de log.")

async def setup(bot: commands.Bot):
    await bot.add_cog(NomeNoCanalCog(bot))
