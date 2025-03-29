import re
import discord
from discord.ext import commands
import asyncio

from db import SessionLocal, PlayerName

# Regex para checar se o apelido está em [NomeDoJogo] - NomeDiscord
NICK_REGEX = re.compile(r'^\[.+\]\s*-\s*.+$')

class NomeNoCanalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Para evitar perguntar múltiplas vezes ao mesmo tempo ao mesmo usuário
        self.waiting_for_name = set()

    # -----------------------------------------------------
    # 1) Interceptar mensagens de quem não está verificado
    # -----------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Se o autor da mensagem não estiver verificado:
         - Apaga a mensagem
         - Envia Embed de termos e pede nome no mesmo canal
         - Aguarda resposta 60s
         - Ajusta apelido, salva no DB e avisa
        """
        # Ignora bots e mensagens em DM
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author
        channel = message.channel

        # Se já verificado, libera
        if await self.is_verified(member):
            return

        # Apaga a mensagem do não-verificado
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Se já estamos esperando esse usuário, não pergunta novamente
        if member.id in self.waiting_for_name:
            return
        self.waiting_for_name.add(member.id)

        # Embed de termos
        embed_pedido = discord.Embed(
            title="Verificação Necessária",
            description=(
                f"{member.mention}, você ainda não definiu seu **nome no jogo**.\n\n"
                "**Termos Básicos**:\n"
                "1. Seu apelido deve ficar no formato `[NomeDoJogo] - NomeDiscord`.\n"
                "2. Ao prosseguir, você concorda com as regras do servidor.\n"
                "3. **Se o nome fornecido não for realmente o mesmo que você usa no jogo, "
                "você poderá ser banido do servidor e do jogo.**\n\n"
                "**Por favor, digite agora seu nome no jogo (você tem 60 segundos).**"
            ),
            color=discord.Color.orange()
        )
        embed_pedido.set_footer(text="Sistema de Verificação")

        await channel.send(embed=embed_pedido)

        # Aguarda a próxima mensagem do mesmo autor
        def check(m: discord.Message):
            return m.author.id == member.id and m.channel.id == channel.id

        try:
            resposta = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            # Tempo esgotado
            embed_timeout = discord.Embed(
                title="Tempo Esgotado",
                description=(
                    f"{member.mention}, você não respondeu a tempo.\n"
                    "Envie outra mensagem a qualquer momento para tentar novamente."
                ),
                color=discord.Color.red()
            )
            await channel.send(embed=embed_timeout)
            self.waiting_for_name.remove(member.id)
            return

        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        # Tenta alterar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            embed_forbidden = discord.Embed(
                title="Erro de Permissão",
                description=(
                    f"{member.mention}, não tenho permissão para alterar seu apelido.\n"
                    "Fale com um administrador!"
                ),
                color=discord.Color.red()
            )
            await channel.send(embed=embed_forbidden)
            self.waiting_for_name.remove(member.id)
            return

        # Salva no DB
        self.salvar_in_game_name(member.id, in_game_name)

        # Embed de sucesso
        embed_sucesso = discord.Embed(
            title="Verificação Concluída",
            description=(
                f"✅ {member.mention}, seu apelido foi definido para **`{novo_nick}`**.\n"
                "Agora você está liberado para conversar!"
            ),
            color=discord.Color.green()
        )
        await channel.send(embed=embed_sucesso)

        self.waiting_for_name.remove(member.id)

    # -----------------------------------------------------
    # 2) Detectar mudança de apelido (opcional)
    # -----------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Se o usuário removeu o formato [NomeDoJogo] - NomeDiscord depois de verificado,
        enviamos um aviso. Se quiser, pode banir ou reverter o apelido automaticamente.
        """
        if before.bot or after.bot:
            return
        if before.nick == after.nick:
            return

        was_verified = (before.nick and NICK_REGEX.match(before.nick))
        is_still_verified = (after.nick and NICK_REGEX.match(after.nick))

        # Se estava verificado e agora não está
        if was_verified and not is_still_verified:
            # Pode mandar aviso num canal público ou num canal de logs
            # Exemplo: mandar aviso no "system channel"
            guild = after.guild
            system_channel = guild.system_channel
            if system_channel:
                embed_alert = discord.Embed(
                    title="Alerta de Nickname",
                    description=(
                        f"{after.mention}, você removeu o prefixo `[NomeDoJogo] - ...` do seu apelido.\n"
                        "Por favor, mantenha o formato correto ou poderá ser punido!"
                    ),
                    color=discord.Color.yellow()
                )
                await system_channel.send(embed=embed_alert)

            # Se quiser banir ou reverter o apelido, descomente:
            # try:
            #     await after.edit(nick=before.nick)
            # except discord.Forbidden:
            #     pass
            # OU ban:
            # await after.ban(reason="Removeu prefixo após verificação.")

    # -----------------------------------------------------
    # 3) Funções auxiliares
    # -----------------------------------------------------
    async def is_verified(self, member: discord.Member) -> bool:
        """
        Retorna True se o membro:
          1. Tiver apelido no formato [NomeDoJogo] - NomeDiscord, e
          2. Tiver registro no DB (PlayerName).
        """
        if not member.nick or not NICK_REGEX.match(member.nick):
            return False

        session = SessionLocal()
        try:
            registro = session.query(PlayerName).filter_by(discord_id=str(member.id)).first()
            return bool(registro)  # True se encontrou registro
        except:
            return False
        finally:
            session.close()

    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """
        Insere ou atualiza in_game_name no DB.
        """
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
