import re
import discord
from discord.ext import commands
import asyncio

from db import SessionLocal, PlayerName

class NomeCog(commands.Cog):
    """
    Cog que gerencia apelidos no formato [NomeJogo] - NomeDiscord.
    Salva o nome do jogo na tabela 'player_name'.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Expressão regular para checar o formato: [algo] - algo
        self.pattern = re.compile(r'^\[.+\]\s*-\s*.+$')

    # ==================================================
    # 1. Quando um membro entra, verifica se tem apelido
    # ==================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Quando o membro entra, se não estiver com o apelido no formato, solicitamos via DM."""
        if member.bot:
            return

        # Se não tiver apelido ou não casar com o padrão, solicitar
        if not member.nick or not self.pattern.match(member.nick):
            await self.solicitar_nome_jogo(member)

    # ==================================================
    # 2. Detectar mudança de apelido
    # ==================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Se o membro alterar o apelido e remover o formato [Jogo] - Nome,
        avisamos por DM e podemos (opcionalmente) restaurar.
        """
        if before.bot or after.bot:
            return

        if before.nick == after.nick:
            return  # Não houve mudança no apelido

        # Se o novo apelido não estiver no formato...
        if after.nick and not self.pattern.match(after.nick):
            try:
                await after.send(
                    "⚠️ Você alterou seu apelido e ele não está mais no formato "
                    "`[SeuNomeNoJogo] - SeuNomeDiscord`. "
                    "Por favor, mantenha o formato correto."
                )
            except discord.Forbidden:
                pass

            # Se quiser forçar a voltar ao apelido anterior, pode fazer assim:
            # if before.nick and self.pattern.match(before.nick):
            #     try:
            #         await after.edit(nick=before.nick)
            #     except discord.Forbidden:
            #         pass

    # ==================================================
    # 3. Bloquear mensagem de quem não está no formato
    # ==================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Se o membro não está no formato [nome_jogo] - nome_discord,
        apagamos a mensagem e enviamos DM pedindo correção.
        """
        if message.author.bot:
            return

        # Ignore DMs
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        if not member.nick or not self.pattern.match(member.nick):
            # Apaga a mensagem
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # Avisa por DM
            try:
                await member.send(
                    "❌ Você não pode enviar mensagens no servidor sem definir seu apelido "
                    "no formato `[NomeDoJogo] - SeuNomeDiscord`.\n\n"
                    "Qual é seu nome no jogo?"
                )
            except discord.Forbidden:
                pass

    # ==================================================
    # 4. Perguntar e configurar o apelido
    # ==================================================
    async def solicitar_nome_jogo(self, member: discord.Member):
        """
        Envia DM para o usuário, pergunta o nome do jogo
        e ajusta o apelido para [NomeJogo] - NomeDiscord.
        """
        # Cria canal de DM
        try:
            dm_channel = await member.create_dm()
            await dm_channel.send(
                "Olá! Percebi que você não está com seu apelido no formato `[NomeDoJogo] - NomeDiscord`.\n"
                "Por favor, me diga: **qual é seu nome no jogo?**"
            )
        except discord.Forbidden:
            return  # Se não consegue DM, nada a fazer

        # Espera resposta
        def check(m: discord.Message):
            return m.author == member and m.channel == dm_channel

        try:
            resposta = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await dm_channel.send("Você não respondeu a tempo. Tente novamente!")
            return

        in_game_name = resposta.content.strip()

        # Define apelido: [NomeDoJogo] - NomeDiscord
        novo_nick = f"[{in_game_name}] - {member.name}"
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await dm_channel.send(
                "Não consegui alterar seu apelido (permissões insuficientes). "
                "Contate um administrador."
            )
            return

        # Salvar no banco
        self.salvar_in_game_name(member.id, in_game_name)

        await dm_channel.send(
            f"✅ Seu apelido foi atualizado para `{novo_nick}`! Obrigado."
        )

    # ==================================================
    # 5. Salvar no banco de dados
    # ==================================================
    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """Salva ou atualiza o nome do jogo na tabela player_name."""
        session = SessionLocal()
        try:
            registro = session.query(PlayerName).filter_by(discord_id=str(discord_id)).first()
            if registro:
                registro.in_game_name = in_game_name
            else:
                novo_registro = PlayerName(discord_id=str(discord_id), in_game_name=in_game_name)
                session.add(novo_registro)

            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Erro ao salvar o nome do jogo no DB: {e}")
        finally:
            session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(NomeCog(bot))
