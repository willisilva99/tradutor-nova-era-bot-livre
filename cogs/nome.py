import re
import discord
from discord.ext import commands
import asyncio

from db import SessionLocal, PlayerName

# Regex opcional para checar se o apelido está em [NomeDoJogo] - NomeDiscord
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

class NomeNoCanalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Para evitar perguntar múltiplas vezes ao mesmo tempo ao mesmo usuário
        self.waiting_for_name = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Sempre que alguém falar num canal (não DM), se não estiver verificado:
         1) Apaga a mensagem.
         2) Pergunta o nome no jogo no mesmo canal (se já não estivermos esperando).
         3) Aguarda resposta nesse canal.
         4) Altera apelido e salva no DB.
        """
        # Ignora bots e mensagens em DM
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel

        # Checa se já está "verificado": 
        #   a) Tem apelido no formato [xxx] - yyy, OU
        #   b) Está no DB (opcional) – Se quiser forçar DB e apelido, mude a checagem
        if await self.is_verified(member):
            return  # Liberado para falar

        # Se não está verificado, apaga a mensagem
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Se já estamos esperando esse usuário responder, não faz nada
        if member.id in self.waiting_for_name:
            return

        # Marca que estamos esperando
        self.waiting_for_name.add(member.id)

        # Pergunta o nome no jogo
        pergunta = await channel.send(
            f"{member.mention}, você ainda não definiu seu nome no jogo.\n"
            "Por favor, **diga agora** qual é seu nome no jogo (neste canal)."
        )

        # Aguarda a próxima mensagem do mesmo autor
        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            # Tempo esgotado
            await channel.send(
                f"{member.mention}, você não respondeu a tempo. "
                "Tente enviar uma nova mensagem se quiser tentar de novo."
            )
            self.waiting_for_name.remove(member.id)
            return

        # Pegou a resposta
        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        # Tenta alterar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(
                f"{member.mention}, não tenho permissão para alterar seu apelido. "
                "Fale com um administrador!"
            )
            self.waiting_for_name.remove(member.id)
            return

        # Salva no DB
        self.salvar_in_game_name(member.id, in_game_name)

        await channel.send(
            f"✅ {member.mention}, seu apelido foi definido para `{novo_nick}`. "
            "Agora você está liberado para conversar!"
        )

        # Tira do set de "espera"
        self.waiting_for_name.remove(member.id)

    async def is_verified(self, member: discord.Member) -> bool:
        """
        Retorna True se o membro:
          - Tiver apelido no formato [NomeDoJogo] - NomeDiscord, e
          - Estiver no DB (opcional) – Ajuste a lógica como quiser.
        """
        # Checa apelido
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False

        # Se quiser checar no DB se existe
        session = SessionLocal()
        try:
            registro = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            if registro:
                # Ele está no DB
                return True
            else:
                return False
        except:
            return False
        finally:
            session.close()

    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """Insere ou atualiza in_game_name no DB."""
        session = SessionLocal()
        try:
            registro = session.query(PlayerName).filter_by(discord_id=str(discord_id)).first()
            if registro:
                registro.in_game_name = in_game_name
            else:
                novo = PlayerName(discord_id=str(discord_id), in_game_name=in_game_name)
                session.add(novo)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] Não foi possível salvar: {e}")
        finally:
            session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(NomeNoCanalCog(bot))
