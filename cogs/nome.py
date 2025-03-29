import discord
from discord.ext import commands
import asyncio

from db import SessionLocal, PlayerName

VERIFICATION_CATEGORY_ID = 1355588765107880188  # ID da categoria "Verificação"
ROLE_AGUARDANDO_ID = 1355588895227511027       # ID do cargo "Aguardando Verificação"
LOG_CHANNEL_ID = 1355589350254968933           # Canal de logs (opcional)
VERIFICATION_TIMEOUT = 300  # 5 minutos
APELIDO_REGEX = r'^\[.+\]\s*-\s*.+$'  # Se quiser checar se o apelido está no formato [xxx] - yyy

class NomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verification_channels = {}

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Quando o bot estiver pronto:
        1) Verifica IDs de categoria/cargo.
        2) Opcional: chama a função para varrer membros já existentes.
        """
        print("NomeCog está pronto. Fazendo verificação de membros existentes...")

        # Chama a função para checar cada membro do(s) servidor(es)
        # Se seu bot estiver em vários servidores, você pode escolher só um.
        for guild in self.bot.guilds:
            await self.verificar_existentes(guild)

    async def verificar_existentes(self, guild: discord.Guild):
        """
        Escaneia todos os membros do servidor.
        Se não estiverem no DB ou apelido fora do formato,
        atribui cargo "Aguardando Verificação" e cria canal.
        """
        print(f"[DEBUG] Verificando membros existentes no servidor: {guild.name} (ID={guild.id})")

        # Pega cargo
        role = guild.get_role(ROLE_AGUARDANDO_ID)
        if not role:
            print(f"[ERRO] Cargo com ID={ROLE_AGUARDANDO_ID} não encontrado em {guild.name}.")
            return

        # Pega categoria
        category = self.bot.get_channel(VERIFICATION_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"[ERRO] Categoria com ID={VERIFICATION_CATEGORY_ID} não encontrada.")
            return

        # Carrega do DB quem já tem registro
        session = SessionLocal()
        try:
            registrados = session.query(PlayerName.discord_id).all()
            registrados_ids = {r[0] for r in registrados}  # set de strings
        finally:
            session.close()

        # Para cada membro, checa se precisa verificação
        for member in guild.members:
            if member.bot:
                continue

            # Se já tem ID no DB, e o apelido bate o formato, ignora
            ja_registrado = str(member.id) in registrados_ids

            nick_ok = False
            if member.nick:
                import re
                nick_ok = re.match(APELIDO_REGEX, member.nick) is not None

            if ja_registrado and nick_ok:
                continue  # esse está ok

            # Se chegou aqui, precisa verificação
            print(f"[DEBUG] Membro {member} precisa verificação. Registrado? {ja_registrado}, NickOK? {nick_ok}")

            # Dá cargo e cria canal (se ainda não tiver canal de verificação)
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="Usuário necessita verificação.")
                except discord.Forbidden:
                    print(f"[ERRO] Sem permissão para atribuir cargo '{role.name}' ao {member}.")

            # Cria canal, se não existir ainda
            await self.criar_canal_verificacao(member, category)

    async def criar_canal_verificacao(self, member: discord.Member, category: discord.CategoryChannel):
        """
        Cria o canal temporário de verificação para um membro.
        """
        # Checa se já criamos um canal para este membro
        if member.id in self.verification_channels:
            # Já temos um canal para ele; talvez não precise criar outro
            channel_id = self.verification_channels[member.id]
            if self.bot.get_channel(channel_id):
                print(f"[DEBUG] Canal de verificação já existe para {member}.")
                return

        channel_name = f"verificacao-{member.name.lower().replace(' ', '-')}"
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            self.bot.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        try:
            verification_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason="Canal temporário de verificação (membro existente)."
            )
            self.verification_channels[member.id] = verification_channel.id
            print(f"[DEBUG] Canal de verificação criado: {verification_channel.name} para {member}.")

            msg_intro = (
                f"Olá {member.mention}! Você ainda não está verificado.\n"
                "Por favor, digite aqui seu **nome no jogo** em até 5 minutos. "
                "Depois disso, este canal será removido."
            )
            await verification_channel.send(msg_intro)

            # Esperar resposta
            await self.aguardar_resposta(member, verification_channel)

        except Exception as e:
            print(f"[ERRO] ao criar canal de verificação para {member}: {e}")

    async def aguardar_resposta(self, member: discord.Member, channel: discord.TextChannel):
        def check(m: discord.Message):
            return m.channel.id == channel.id and m.author.id == member.id

        try:
            resposta = await self.bot.wait_for("message", timeout=VERIFICATION_TIMEOUT, check=check)
        except asyncio.TimeoutError:
            await channel.send("Tempo esgotado! Você não forneceu seu nome. Este canal será excluído.")
            await asyncio.sleep(5)
            await channel.delete(reason="Tempo de verificação esgotado.")
            return

        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send("Não tenho permissão para alterar seu apelido. Contate um administrador!")
            return

        # Salvar no DB
        self.salvar_in_game_name(member.id, in_game_name)

        # Remove cargo
        role = member.guild.get_role(ROLE_AGUARDANDO_ID)
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Usuário verificado com sucesso.")
            except discord.Forbidden:
                pass

        await channel.send(
            f"✅ Obrigado, {member.mention}! Apelido atualizado para `{novo_nick}`. "
            "Removeremos este canal em 5s..."
        )
        await asyncio.sleep(5)
        await channel.delete(reason="Verificação concluída.")
        if member.id in self.verification_channels:
            del self.verification_channels[member.id]

        # Log
        await self.logar(f"O usuário {member} foi verificado como '{in_game_name}' (membro existente).")

    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
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

    async def logar(self, mensagem: str):
        if LOG_CHANNEL_ID:
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if channel:
                try:
                    await channel.send(mensagem)
                except discord.Forbidden:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(NomeCog(bot))
