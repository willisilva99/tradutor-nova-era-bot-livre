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
WAIT_TIME = 90           # Tempo (segundos) para esperar resposta do usuário
LOG_CHANNEL_ID = 978460787586789406  # ID do canal de logs
STAFF_ROLE_ID = 978464190979260426   # ID do cargo da staff
VERIFICADO_ROLE_ID = 978444009536094269  # ID do cargo que será dado ao jogador verificado
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')  # Padrão: [NomeDoJogo] - NomeDiscord

class NomeNoCanalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_for_name = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        if member.id == guild.owner_id:
            return

        if message.content.lower().strip() == "mudar nick":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if not await self.is_verified(member):
                await channel.send(f"{member.mention}, você ainda não está verificado. Por favor, use o processo de verificação normal.")
                return
            await self.prompt_mudar_nick(member, channel)
            return

        if await self.is_verified(member):
            return

        try:
            await message.delete()
        except discord.Forbidden:
            await self.logar(f"[ERRO] Não pude apagar a mensagem de {member} em {channel.mention} (permissão negada).")

        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)

        embed_pedido = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, você ainda não definiu seu **nome no jogo**.\n\n"
                "**Termos Básicos**:\n"
                "1. Ao prosseguir, você concorda com as regras do servidor.\n"
                "2. Se o nome fornecido **não** for realmente o que você usa no jogo, **poderá ser banido**.\n\n"
                "Digite seu nome no jogo e, se desejar, seu nome no Discord separados por vírgula.\n"
                "Exemplo: `Jão, Fulano`\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_pedido.set_image(url="https://i.imgur.com/mApxbuW.gif")  # <- Aqui entra o GIF!
        embed_pedido.set_footer(text="Sistema de Verificação")
        pedido_msg = await channel.send(embed=embed_pedido)

        def check(m):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(
                title="Tempo Esgotado",
                description=(f"{member.mention}, você não respondeu em {WAIT_TIME} segundos.\nTente novamente."),
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            await pedido_msg.delete()
            await timeout_msg.delete()
            return

        try:
            await resposta.delete()
        except discord.Forbidden:
            pass

        parts = resposta.content.split(',')
        game_name = parts[0].strip()
        discord_name = parts[1].strip() if len(parts) > 1 else member.display_name
        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            embed_perm = discord.Embed(
                title="Erro de Permissão",
                description=f"{member.mention}, não consigo alterar seu apelido. Fale com um administrador!",
                color=COR_ERRO
            )
            perm_msg = await channel.send(embed=embed_perm)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            await perm_msg.delete()
            await pedido_msg.delete()
            return

        self.salvar_in_game_name(member.id, novo_nick)

        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\nVocê está liberado para conversar!"),
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=embed_sucesso)

        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Permissão negada ao tentar dar o cargo para {member}")

        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} definiu seu apelido para '{novo_nick}' e foi verificado.")
        await asyncio.sleep(60)
        await pedido_msg.delete()
        await final_msg.delete()

    async def prompt_mudar_nick(self, member, channel):
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)

        embed_mudar = discord.Embed(
            title="Mudar Nickname",
            description=(
                f"{member.mention}, digite seu novo nome no jogo e, se desejar, seu nome no Discord separados por vírgula.\n"
                "Exemplo: `NovoJogo, NovoNome`\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_mudar.set_footer(text="Sistema de Verificação - Mudar Nickname")
        mudar_msg = await channel.send(embed=embed_mudar)

        def check(m):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(
                title="Tempo Esgotado",
                description=(f"{member.mention}, você não respondeu a tempo. Tente novamente mais tarde."),
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            await mudar_msg.delete()
            await timeout_msg.delete()
            return

        await resposta.delete()
        parts = resposta.content.split(',')
        game_name = parts[0].strip()
        discord_name = parts[1].strip() if len(parts) > 1 else member.display_name
        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(f"{member.mention}, não consegui alterar seu apelido. Fale com um administrador.")
            self.waiting_for_name.remove(member.id)
            return

        self.salvar_in_game_name(member.id, novo_nick)

        verificado_role = member.guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Permissão negada ao tentar dar o cargo para {member}")

        embed_sucesso = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=(f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**."),
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")
        await asyncio.sleep(60)
        await mudar_msg.delete()
        await final_msg.delete()

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
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
                description=f"{after.mention}, seu apelido saiu do padrão. Corrija ou poderá ser punido!",
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
                    await self.logar(f"Cargo removido de {after} por alteração de apelido inválido.")
                except discord.Forbidden:
                    await self.logar(f"[ERRO] Não consegui remover o cargo de {after}.")

    async def is_verified(self, member):
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False
        session = SessionLocal()
        try:
            reg = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(reg)
        finally:
            session.close()

    def salvar_in_game_name(self, discord_id, nickname):
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

    async def logar(self, mensagem):
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
