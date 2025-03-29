import discord
from discord.ext import commands
import asyncio

# Importe sua configuração de DB
from db import SessionLocal, PlayerName

# IDs que você precisa ajustar no seu servidor:
VERIFICATION_CATEGORY_ID = 123456789012345678  # ID da categoria "Verificação"
ROLE_AGUARDANDO_ID = 234567890123456789       # ID do cargo "Aguardando Verificação"
LOG_CHANNEL_ID = 345678901234567890           # Opcional: canal de logs

# Tempo de espera (em segundos) para o usuário responder. Ex: 300 = 5 minutos
VERIFICATION_TIMEOUT = 300

class NomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dicionário para mapear qual canal pertence a qual usuário
        # { member_id: channel_id }
        self.verification_channels = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Quando um usuário entra:
         - Dá cargo "Aguardando Verificação"
         - Cria um canal de verificação
         - Pede o nome do jogo
        """
        if member.bot:
            return

        # 1) Atribuir cargo "Aguardando Verificação"
        role = member.guild.get_role(ROLE_AGUARDANDO_ID)
        if role:
            try:
                await member.add_roles(role, reason="Usuário aguardando verificação.")
            except discord.Forbidden:
                print(f"[ERRO] Sem permissão para atribuir cargo ao {member}.")
            except Exception as e:
                print(f"[ERRO] ao atribuir cargo: {e}")

        # 2) Criar canal de verificação
        try:
            verification_cat = self.bot.get_channel(VERIFICATION_CATEGORY_ID)
            if not verification_cat or not isinstance(verification_cat, discord.CategoryChannel):
                print("[ERRO] A categoria de verificação não foi encontrada ou não é CategoryChannel.")
                return

            channel_name = f"verificacao-{member.name.lower().replace(' ', '-')}"
            # Permissões específicas: só o user, o bot (e staff se quiser) podem ver.
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                self.bot.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                # Se quiser staff ver, adicione aqui a role da staff
                # ex.: staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }

            # Cria o canal
            channel = await verification_cat.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason="Canal temporário de verificação"
            )
            self.verification_channels[member.id] = channel.id

            # 3) Mensagem de boas-vindas no canal
            msg_intro = (
                f"Olá {member.mention}! "
                "Bem-vindo ao servidor. Antes de participar, preciso do seu **nome no jogo**.\n\n"
                f"Digite aqui seu nome no jogo dentro de {VERIFICATION_TIMEOUT//60} minutos. "
                "Depois disso, este canal será removido!"
            )
            await channel.send(msg_intro)

            # 4) Esperar resposta
            await self.aguardar_resposta(member, channel)

        except Exception as e:
            print(f"[ERRO] ao criar canal de verificação para {member}: {e}")

    async def aguardar_resposta(self, member: discord.Member, channel: discord.TextChannel):
        """
        Espera pelo nome do jogo do usuário no canal de verificação.
        Se der timeout, deleta o canal.
        Caso contrário, seta o apelido e remove cargo.
        """
        def check(m: discord.Message):
            return m.channel.id == channel.id and m.author.id == member.id
        
        try:
            resposta = await self.bot.wait_for('message', timeout=VERIFICATION_TIMEOUT, check=check)
        except asyncio.TimeoutError:
            # Se o usuário não respondeu
            await channel.send("Tempo esgotado! Você não forneceu seu nome. Este canal será excluído.")
            await asyncio.sleep(5)
            await channel.delete(reason="Tempo de verificação esgotado.")
            return

        # O usuário mandou algo
        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        # Tenta editar apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await channel.send(
                "Não tenho permissão para alterar seu apelido. "
                "Contate um administrador!"
            )
            return

        # Salvar no banco
        self.salvar_in_game_name(member.id, in_game_name)

        # Remove o cargo "Aguardando Verificação"
        role = member.guild.get_role(ROLE_AGUARDANDO_ID)
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Usuário verificado com sucesso.")
            except discord.Forbidden:
                pass

        await channel.send(
            f"✅ Obrigado, {member.mention}! Seu apelido foi atualizado para `{novo_nick}`. "
            "Você já pode participar do servidor. Apagaremos este canal em 5 segundos..."
        )
        # Espera uns segundos e deleta o canal
        await asyncio.sleep(5)
        await channel.delete(reason="Verificação concluída.")

        # Remover do dicionário local
        if member.id in self.verification_channels:
            del self.verification_channels[member.id]

        # Logar, se desejar
        await self.logar(f"O usuário {member} foi verificado como '{in_game_name}' e canal de verificação removido.")

    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """Salva ou atualiza o nome no jogo no DB."""
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
        """Opcional: envia logs de verificação para um canal staff."""
        if LOG_CHANNEL_ID:
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if channel:
                try:
                    await channel.send(mensagem)
                except discord.Forbidden:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(NomeCog(bot))
