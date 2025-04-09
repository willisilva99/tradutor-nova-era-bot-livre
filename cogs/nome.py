import re
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

from db import SessionLocal, PlayerName

########################################
# CONFIGURAÇÕES DE CORES (Padronização)
########################################
COR_PADRAO  = discord.Color.from_rgb(255, 165, 0)   # Laranja
COR_SUCESSO = discord.Color.green()
COR_ERRO    = discord.Color.red()
COR_ALERTA  = discord.Color.yellow()

########################################
# OUTRAS CONFIGURAÇÕES
########################################
WAIT_TIME = 60                                     # Tempo de espera (segundos) para resposta
LOG_CHANNEL_ID = 978460787586789406                # ID do canal de logs
STAFF_ROLE_ID = 978464190979260426                 # ID do cargo da staff
VERIFICADO_ROLE_ID = 978444009536094269            # ID do cargo de verificado
VERIFICATION_CHANNEL_ID = 1359135729409589468       # ID do canal de verificação

# Regex para validação interna do formato (não exibido para o membro)
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

class VerificacaoCog(commands.Cog):
    """
    Cog que gerencia a verificação de nickname via canal de verificação.
    O membro envia sua tentativa no canal e o bot processa os dados.
    Se ocorrerem 3 erros, o bot envia uma mensagem instrucional por 30 segundos.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Para armazenar IDs dos membros que estão aguardando resposta
        self.waiting_for_name = set()
        # Contador de erros por usuário (member.id => erro_count)
        self.error_counts = {}

    # ----------------------------------------------------------------------
    # on_message: Processa mensagens apenas no canal de verificação
    # ----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Processa somente mensagens enviadas no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        # Ignora bots e DMs
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel
        guild = member.guild

        # Ignora o dono do servidor
        if member.id == guild.owner_id:
            return

        # Caso o membro já esteja verificado (apelo e registro no DB), apaga a mensagem
        if await self.is_verified(member):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        # Se o usuário enviar "mudar nick", esse caso será tratado no comando slash
        if message.content.lower().strip() == "mudar nick":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            # Se não estiver verificado, não permite alteração
            if not await self.is_verified(member):
                await channel.send(f"{member.mention}, você ainda não está verificado. Use o fluxo de verificação normal.")
                return
            await self.prompt_mudar_nick(member, channel)
            return

        # Se já estiver aguardando a resposta, apaga mensagens extras
        if member.id in self.waiting_for_name:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        self.waiting_for_name.add(member.id)

        pedido_embed = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, para se verificar, digite seu nome no jogo e, opcionalmente, seu novo nome no Discord separados por vírgula.\n"
                "Exemplo: `Jão, Fulano`\n\n"
                "**Termos:** Se o nome informado não for realmente o que você usa no jogo, poderá ser banido do servidor e do jogo.\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        pedido_embed.set_footer(text="Sistema de Verificação")
        pedido_msg = await channel.send(embed=pedido_embed)

        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            # Incrementa o contador de erros
            self.increment_error(member.id)
            timeout_embed = discord.Embed(
                title="Tempo Esgotado",
                description=f"{member.mention}, você não respondeu em {WAIT_TIME} segundos.\nTente novamente enviando os dados corretamente.",
                color=COR_ERRO
            )
            timeout_msg = await channel.send(embed=timeout_embed)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            try:
                await pedido_msg.delete()
                await timeout_msg.delete()
            except discord.Forbidden:
                pass
            # Se o usuário errar 3 vezes, envia mensagem instrucional
            if self.error_counts.get(member.id, 0) >= 3:
                await self.enviar_instrucao(member, channel)
                self.error_counts[member.id] = 0
            return

        try:
            await resposta.delete()  # Apaga a resposta para manter o canal limpo
        except discord.Forbidden:
            pass

        # Extrai os dados enviados
        game_name, discord_name = extrair_dados(resposta.content, member)
        if not game_name:
            # Caso não tenha fornecido um nome válido, trata como erro
            self.increment_error(member.id)
            error_embed = discord.Embed(
                title="Erro na Verificação",
                description=f"{member.mention}, você não inseriu um nome válido para o jogo. Tente novamente.",
                color=COR_ERRO
            )
            error_msg = await channel.send(embed=error_embed)
            self.waiting_for_name.remove(member.id)
            await asyncio.sleep(60)
            try:
                await pedido_msg.delete()
                await error_msg.delete()
            except discord.Forbidden:
                pass
            if self.error_counts.get(member.id, 0) >= 3:
                await self.enviar_instrucao(member, channel)
                self.error_counts[member.id] = 0
            return

        novo_nick = f"[{game_name}] - {discord_name}"

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            perm_embed = discord.Embed(
                title="Erro de Permissão",
                description=f"{member.mention}, não consigo alterar seu apelido. Fale com um administrador.",
                color=COR_ERRO
            )
            perm_msg = await channel.send(embed=perm_embed)
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

        self.salvar_in_game_name(member.id, novo_nick)

        verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
        if verificado_role and verificado_role not in member.roles:
            try:
                await member.add_roles(verificado_role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado a {member}.")

        sucesso_embed = discord.Embed(
            title="Verificação Concluída",
            description=f"✅ {member.mention}, seu apelido agora é **`{novo_nick}`**.\nVocê está verificado e liberado para conversar!",
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=sucesso_embed)
        self.waiting_for_name.remove(member.id)
        self.error_counts[member.id] = 0  # Reseta contador de erros após sucesso
        await self.logar(f"O usuário {member} verificou seu apelido como '{novo_nick}'.")

        # Apaga os embeds de pedido e de sucesso após 60 segundos
        await asyncio.sleep(60)
        try:
            await pedido_msg.delete()
            await final_msg.delete()
        except discord.Forbidden:
            pass

    # -------------------------------------------------------------------
    # Comando Slash para Alterar Nick (para membros já verificados)
    # -------------------------------------------------------------------
    @app_commands.command(name="mudar_nick", description="Altera seu apelido verificado.")
    async def mudar_nick(self, interaction: discord.Interaction, dados: str):
        member = interaction.user
        guild = member.guild
        channel = interaction.channel

        # Verifica se o canal é o de verificação
        if channel.id != VERIFICATION_CHANNEL_ID:
            await interaction.response.send_message("Este comando só pode ser usado no canal de verificação.", ephemeral=True)
            return

        if not await self.is_verified(member):
            await interaction.response.send_message("Você ainda não está verificado. Use o comando /verify para se verificar.", ephemeral=True)
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

        sucesso_embed = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        await interaction.response.send_message(embed=sucesso_embed, ephemeral=True)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")

    # -------------------------------------------------------------------
    # Fluxo para alterar nick quando "mudar nick" é enviado no canal
    # -------------------------------------------------------------------
    async def prompt_mudar_nick(self, member: discord.Member, channel: discord.TextChannel):
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)
        embed_mudar = discord.Embed(
            title="Alteração de Nickname",
            description=(
                f"{member.mention}, para alterar seu apelido, digite seu novo nome no jogo e, se desejar, "
                "seu novo nome no Discord separados por vírgula.\n"
                "Exemplo: `NovoJogo, NovoNome`\n"
                f"Você tem {WAIT_TIME} segundos para responder."
            ),
            color=COR_PADRAO
        )
        embed_mudar.set_footer(text="Sistema de Verificação - Alterar Nickname")
        mudar_msg = await channel.send(embed=embed_mudar)

        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=WAIT_TIME, check=check)
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="Tempo Esgotado",
                description=f"{member.mention}, você não respondeu a tempo para alterar seu apelido. Tente novamente.",
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

        game_name, discord_name = extrair_dados(resposta.content, member)
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
                await self.logar(f"[ERRO] Não pude atribuir o cargo de verificado a {member}.")

        embed_sucesso = discord.Embed(
            title="Alteração de Nickname Concluída",
            description=f"✅ {member.mention}, seu novo apelido é **`{novo_nick}`**.",
            color=COR_SUCESSO
        )
        final_msg = await channel.send(embed=embed_sucesso)
        self.waiting_for_name.remove(member.id)
        await self.logar(f"O usuário {member} alterou seu apelido para '{novo_nick}'.")
        await asyncio.sleep(60)
        try:
            await mudar_msg.delete()
            await final_msg.delete()
        except discord.Forbidden:
            pass

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
            # Remove o cargo de verificado
            verificado_role = guild.get_role(VERIFICADO_ROLE_ID)
            if verificado_role and verificado_role in after.roles:
                try:
                    await after.remove_roles(verificado_role)
                    await self.logar(f"Cargo removido de {after} por alteração inválida de apelido.")
                except discord.Forbidden:
                    await self.logar(f"[ERRO] Não consegui remover o cargo de {after}.")

    # -------------------------------------------------------------------
    # Função auxiliar: checa se o membro está verificado (nick no formato e registro no DB)
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
    # Função auxiliar: Log de ações
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
    # Função auxiliar: Incrementa a contagem de erros para um membro e envia instrução se 3 erros
    # -------------------------------------------------------------------
    async def enviar_instrucao(self, member: discord.Member, channel: discord.TextChannel):
        instr_embed = discord.Embed(
            title="Dica para Verificação",
            description=(
                "Para se verificar, envie seu nome no jogo e, se desejar, seu nome no Discord, separados por vírgula.\n"
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

    def increment_error(self, member_id: int):
        count = self.error_counts.get(member_id, 0) + 1
        self.error_counts[member_id] = count

    # Opcional: Resetar erros quando a verificação ocorrer com sucesso
    def reset_error(self, member_id: int):
        if member_id in self.error_counts:
            self.error_counts[member_id] = 0

async def extrair_dados(input_str: str, member: discord.Member) -> tuple:
    """
    Extrai os dados do input. Se o usuário separar por vírgula,
    o primeiro valor é o nome do jogo e o segundo é o nome do Discord;
    caso contrário, o nome do Discord permanece como o display_name.
    """
    parts = input_str.split(',')
    game = parts[0].strip()
    discord_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else member.display_name
    return game, discord_name

async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
