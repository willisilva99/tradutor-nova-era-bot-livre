import re
import discord
from discord.ext import commands
import asyncio

# Importamos SessionLocal e PlayerName diretamente do db.py
from db import SessionLocal, PlayerName

class NomeCog(commands.Cog):
    """
    Cog que gerencia apelidos no formato [NomeJogo] - NomeDiscord,
    salvando o nome do jogo na tabela 'player_name'.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Expressão regular para checar se o nick está no formato [alguma coisa] - alguma coisa
        self.pattern = re.compile(r'^\[.+\]\s*-\s*.+$')

    # ==================================================
    # 1) Ao novo membro entrar, checamos o apelido
    # ==================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Quando o membro entra, se não estiver no formato [NomeJogo] - NomeDiscord,
        solicitamos via DM o nome do jogo para ajustar o apelido.
        """
        if member.bot:
            return

        if not member.nick or not self.pattern.match(member.nick):
            await self.solicitar_nome_jogo(member)

    # ==================================================
    # 2) Ao mudar o apelido, conferir se perdeu o formato
    # ==================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Se o usuário mudar o apelido e tirar o [NomeJogo] - NomeDiscord,
        podemos avisar para que ele corrija, ou mesmo reverter se quiser.
        """
        if before.bot or after.bot:
            return

        # Se não houve mudança no apelido, não faz nada
        if before.nick == after.nick:
            return

        # Se o novo apelido não bate com a RegEx, avisar
        if after.nick and not self.pattern.match(after.nick):
            try:
                await after.send(
                    "⚠️ Você alterou seu apelido e ele não está mais no formato "
                    "`[NomeDoJogo] - SeuNomeDiscord`. "
                    "Por favor, mantenha o formato correto."
                )
            except discord.Forbidden:
                pass

            # Se quiser forçar a reverter, você pode (cuidado para evitar loop):
            # if before.nick and self.pattern.match(before.nick):
            #     try:
            #         await after.edit(nick=before.nick)
            #     except discord.Forbidden:
            #         pass

    # ==================================================
    # 3) Bloquear mensagens de quem não segue o formato
    # ==================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Se o usuário não estiver com o formato [NomeJogo] - NomeDiscord,
        apaga a mensagem do canal e manda uma DM solicitando ajuste.
        """
        if message.author.bot:
            return

        # Ignora DMs, só aplica em canais do servidor
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        # Verifica se está no formato correto
        if not member.nick or not self.pattern.match(member.nick):
            # Apaga a mensagem
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # Envia aviso por DM
            try:
                await member.send(
                    "❌ Você não pode enviar mensagens no servidor sem definir seu apelido "
                    "no formato `[NomeDoJogo] - SeuNomeDiscord`.\n\n"
                    "Por favor, me diga agora: **qual é seu nome no jogo?**"
                )
            except discord.Forbidden:
                pass

    # ==================================================
    # 4) Perguntar e ajustar apelido
    # ==================================================
    async def solicitar_nome_jogo(self, member: discord.Member):
        """
        Manda DM perguntando qual é o nome no jogo e ajusta apelido para
        [NomeDoJogo] - NomeDiscord, salvando no banco de dados.
        """
        try:
            dm_channel = await member.create_dm()
            await dm_channel.send(
                "Olá! Percebi que você não está com o apelido no formato `[NomeDoJogo] - NomeDiscord`.\n"
                "Por favor, me diga agora: **qual é seu nome no jogo?**"
            )
        except discord.Forbidden:
            # Se não pode mandar DM, não faz nada ou loga para administradores
            return

        def check(m: discord.Message):
            return m.author == member and m.channel == dm_channel

        try:
            # Aguarda até 60s uma resposta do usuário
            resposta = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await dm_channel.send("Você não respondeu a tempo. Tente novamente quando puder!")
            return

        in_game_name = resposta.content.strip()

        # Define o apelido: [NomeNoJogo] - NomeDiscord (ou substitua .name por .display_name)
        novo_nick = f"[{in_game_name}] - {member.name}"
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await dm_channel.send(
                "Não consegui alterar seu apelido (permissões insuficientes). "
                "Entre em contato com um administrador!"
            )
            return

        # Salva no banco de dados
        self.salvar_in_game_name(member.id, in_game_name)

        await dm_channel.send(f"✅ Seu apelido foi atualizado para `{novo_nick}`. Obrigado!")

    # ==================================================
    # 5) Salvar no banco de dados
    # ==================================================
    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """
        Abre uma sessão no banco de dados e salva/atualiza o 'in_game_name'
        na tabela 'player_name' (PlayerName).
        """
        session = SessionLocal()
        try:
            registro = session.query(PlayerName).filter_by(discord_id=str(discord_id)).first()
            if registro:
                # Atualiza se já existir
                registro.in_game_name = in_game_name
            else:
                # Cria registro novo se não existir
                novo = PlayerName(discord_id=str(discord_id), in_game_name=in_game_name)
                session.add(novo)

            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] Não foi possível salvar o nome do jogo: {e}")
        finally:
            session.close()

# Função de setup do cog
async def setup(bot: commands.Bot):
    await bot.add_cog(NomeCog(bot))
