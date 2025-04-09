import re
import time
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from discord import app_commands

########################################
# CONFIGURAÇÕES / IDs
########################################
COR_SUCESSO = discord.Color.green()
COR_ERRO    = discord.Color.red()
COR_ALERTA  = discord.Color.yellow()

VERIFICATION_CHANNEL_ID = 1234567890123456
VERIFICADO_ROLE_ID      = 111222333444  # Cargo de verificado
STAFF_ROLE_ID           = 555666777888  # Cargo da staff
LOG_CHANNEL_ID          = 999888777666  # Canal de logs

# Regex para checar apelido no formato [alguma coisa] - alguma coisa
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

def validar_nomes(game_name: str, discord_name: str) -> tuple[bool, str]:
    """
    Aplica validações mínimas:
    - Cada um com pelo menos 3 caracteres (ignorar espaços)
    - Montagem final não exceder 32 chars (checamos depois)
    Retorna (True, "") se válido, ou (False, "Motivo do erro") se inválido.
    """
    if len(game_name.replace(" ", "")) < 3:
        return False, "O nome do jogo deve ter ao menos 3 caracteres."
    if len(discord_name.replace(" ", "")) < 3:
        return False, "O nome do Discord deve ter ao menos 3 caracteres."
    return True, ""

class VerificacaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------
    #    LISTENER on_message: foco total no canal de verificação
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora se não for no canal de verificação
        if message.channel.id != VERIFICATION_CHANNEL_ID:
            return
        # Ignora bots
        if message.author.bot:
            return

        member = message.author
        guild = member.guild

        # Se for o dono do servidor, ignora sem apagar
        if member.id == guild.owner_id:
            return

        # (1) Se o membro já é verificado, apaga qualquer mensagem dele.
        if await self.is_verified(member):
            await self.apagar_mensagem(message)
            return

        # Se o cara digitou "mudar nick" (ou qualquer outra coisa),
        # vamos tentar processar como verificação textual. 
        # Caso esteja fora do padrão, apaga a mensagem de qualquer forma.

        # Exemplo de split: "NomeDoJogo, NomeDiscord"
        parts = message.content.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            # Se não forneceu nada depois da vírgula, use display_name
            # (ou exija sempre?)
            discord_name = member.display_name

        # Valida
        ok, erro = validar_nomes(game_name, discord_name)
        if not ok:
            # Manda embed de erro temporário, apaga a mensagem do user
            await self.mandar_erro_e_apagar(message, f"{member.mention}, {erro}")
            return

        # Monta apelido final
        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await self.mandar_erro_e_apagar(
                message,
                f"{member.mention}, o apelido final ultrapassa **32 caracteres**. Tente encurtar."
            )
            return

        # Tenta alterar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            # Se não tiver permissão, apenas avisa e apaga a msg
            await self.mandar_erro_e_apagar(
                message,
                f"{member.mention}, não tenho permissão/hierarquia para alterar seu apelido."
            )
            return
        except Exception as e:
            await self.logar(f"[ERRO] ao editar apelido de {member}: {e}")
            await self.mandar_erro_e_apagar(
                message,
                f"{member.mention}, ocorreu um erro inesperado ao alterar seu apelido."
            )
            return

        # Se chegou até aqui, deu certo
        # [Opcional] Salva no BD (se você tiver a função):
        # self.salvar_in_game_name(member.id, novo_nick)

        # Tenta atribuir cargo de verificado
        role = guild.get_role(VERIFICADO_ROLE_ID)
        if role and role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude adicionar cargo verificado a {member}.")

        # Reage com ✅ para indicar sucesso
        try:
            await message.add_reaction("✅")
        except discord.Forbidden:
            pass

        # Manda embed de sucesso
        embed = discord.Embed(
            title="Verificação Concluída",
            description=(
                f"{member.mention}, seu apelido foi definido como:\n"
                f"**`{novo_nick}`**.\nSeja bem-vindo(a)!"
            ),
            color=COR_SUCESSO
        )
        msg_sucesso = await message.channel.send(embed=embed)
        await self.logar(f"O usuário {member} se verificou como '{novo_nick}'.")

        # [Opcional] Apagar o embed de sucesso após X segundos
        await asyncio.sleep(15)
        try:
            await msg_sucesso.delete()
        except discord.Forbidden:
            pass

        # OBS: Note que **não** apagamos a mensagem correta do usuário
        # pois você quer manter a "verificação correta" sem apagar.
        # Caso queira apagar mesmo assim, basta chamar `await self.apagar_mensagem(message)` também.

    # ------------------------------------------------------------
    #   on_member_update: se o nick sair do padrão, remove cargo
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or after.id == after.guild.owner_id:
            return
        if before.nick == after.nick:
            return

        was_verified = before.nick and NICK_REGEX.match(before.nick)
        is_still_verified = after.nick and NICK_REGEX.match(after.nick)

        if was_verified and not is_still_verified:
            # Avisamos no system_channel e removemos cargo de verificado
            guild = after.guild
            system_channel = guild.system_channel
            if system_channel:
                embed = discord.Embed(
                    title="Alerta de Nickname",
                    description=(
                        f"{after.mention}, seu apelido saiu do formato. "
                        "Você perderá o cargo de verificado!"
                    ),
                    color=COR_ALERTA
                )
                await system_channel.send(embed=embed)

            role = guild.get_role(VERIFICADO_ROLE_ID)
            if role and role in after.roles:
                try:
                    await after.remove_roles(role)
                    await self.logar(f"Removeu cargo verificado de {after}, apelido inválido.")
                except discord.Forbidden:
                    await self.logar(f"Não consegui remover cargo verificado de {after}.")

    # ------------------------------------------------------------
    #   Slash command /mudar_nick
    #   (Se quiser que mantenha mesmo regime de apagar msg, 
    #   lembre que slash commands não geram 'mensagem' do usuário.)
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

        # Se não está verificado, poderia forçar a verificação normal
        # ou permitir mesmo assim. Fica a seu critério:
        # if not await self.is_verified(member):
        #     ...

        parts = dados.split(',')
        game_name = parts[0].strip()
        if len(parts) > 1:
            discord_name = parts[1].strip()
        else:
            discord_name = member.display_name

        # Validação
        ok, erro = validar_nomes(game_name, discord_name)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return

        novo_nick = f"[{game_name}] - {discord_name}"
        if len(novo_nick) > 32:
            await interaction.response.send_message(
                "O apelido final ultrapassa 32 caracteres. Tente encurtar.",
                ephemeral=True
            )
            return

        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar seu apelido.",
                ephemeral=True
            )
            return
        except Exception as e:
            await self.logar(f"[ERRO] Slash /mudar_nick: {e}")
            await interaction.response.send_message("Erro inesperado.", ephemeral=True)
            return

        # Tenta adicionar cargo verificado
        role = guild.get_role(VERIFICADO_ROLE_ID)
        if role and role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                await self.logar(f"[ERRO] Não pude adicionar cargo verificado ao {member}.")

        await interaction.response.send_message(
            f"Seu apelido foi alterado para: `{novo_nick}`",
            ephemeral=True
        )

    # ------------------------------------------------------------
    #   is_verified (checa via regex ou cargo, etc.)
    # ------------------------------------------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        # Aqui pode checar só cargo OU cargo+regex
        # Se quiser checar DB, fique à vontade. Exemplo:
        # if not member.nick or not NICK_REGEX.match(member.nick):
        #     return False
        # return True se cargo de verificado
        role = member.guild.get_role(VERIFICADO_ROLE_ID)
        return bool(role and (role in member.roles))

    # ------------------------------------------------------------
    #   Apagar mensagem com try/except
    # ------------------------------------------------------------
    async def apagar_mensagem(self, message: discord.Message):
        try:
            await message.delete()
        except discord.Forbidden:
            pass

    # ------------------------------------------------------------
    #   Mandar embed de erro temporário e apagar a msg do user
    # ------------------------------------------------------------
    async def mandar_erro_e_apagar(self, message: discord.Message, texto: str):
        embed = discord.Embed(
            title="Erro de Verificação",
            description=texto,
            color=COR_ERRO
        )
        msg_erro = await message.channel.send(embed=embed)
        # Apaga a mensagem do user
        await self.apagar_mensagem(message)
        # Apaga a mensagem de erro após ~10s
        await asyncio.sleep(10)
        try:
            await msg_erro.delete()
        except discord.Forbidden:
            pass

    # ------------------------------------------------------------
    #   Logar ações no canal de logs
    # ------------------------------------------------------------
    async def logar(self, texto: str):
        canal_log = self.bot.get_channel(LOG_CHANNEL_ID)
        if canal_log:
            try:
                data_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await canal_log.send(f"[{data_str}] {texto}")
            except discord.Forbidden:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(VerificacaoCog(bot))
