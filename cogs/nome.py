import discord
from discord.ext import commands
import asyncio

from db import SessionLocal, PlayerName

###########################
# CONFIGURAÇÕES
###########################
VERIFICATION_CATEGORY_ID = 1355588765107880188  # ID da categoria "Verificação"
ROLE_AGUARDANDO_ID = 1355588895227511027       # ID do cargo "Aguardando Verificação"
LOG_CHANNEL_ID = 1355589350254968933           # Canal de logs (opcional)
VERIFICATION_TIMEOUT = 300                     # Tempo em segundos (5min)

class NomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Armazena {member_id: channel_id} caso precise
        self.verification_channels = {}

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Evento chamado quando o bot termina de inicializar.
        Vamos apenas imprimir que tudo está ok e
        checar se a categoria e o cargo de verificação existem.
        """
        print("[DEBUG] NomeCog está pronto. Verificando IDs...")

        # Vamos checar se a categoria existe
        cat = self.bot.get_channel(VERIFICATION_CATEGORY_ID)
        if cat is None:
            print(f"[ERRO] Categoria com ID={VERIFICATION_CATEGORY_ID} não encontrada!")
        else:
            if isinstance(cat, discord.CategoryChannel):
                print(f"[DEBUG] Categoria '{cat.name}' (ID={cat.id}) encontrada.")
            else:
                print(f"[ERRO] Objeto com ID={VERIFICATION_CATEGORY_ID} não é uma CategoryChannel.")

        # Verificar se o cargo existe em pelo menos um servidor
        role_found = False
        for guild in self.bot.guilds:
            role = guild.get_role(ROLE_AGUARDANDO_ID)
            if role is not None:
                print(f"[DEBUG] Cargo '{role.name}' (ID={role.id}) encontrado no servidor '{guild.name}'.")
                role_found = True
        if not role_found:
            print(f"[ERRO] Cargo com ID={ROLE_AGUARDANDO_ID} não foi encontrado em nenhum servidor.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Quando um usuário entra no servidor, damos cargo "Aguardando Verificação",
        criamos um canal temporário para ele e pedimos o nome do jogo.
        """
        if member.bot:
            return

        print(f"[DEBUG] on_member_join: {member} entrou no servidor {member.guild.name}.")

        # Atribuir cargo
        role = member.guild.get_role(ROLE_AGUARDANDO_ID)
        if role:
            try:
                await member.add_roles(role, reason="Usuário aguardando verificação.")
                print(f"[DEBUG] Cargo '{role.name}' adicionado a {member}.")
            except discord.Forbidden:
                print(f"[ERRO] Sem permissão para atribuir cargo '{role.name}' ao {member}.")
            except Exception as e:
                print(f"[ERRO] ao atribuir cargo '{role.name}': {e}")
        else:
            print(f"[ERRO] Role ID={ROLE_AGUARDANDO_ID} não encontrado no guild '{member.guild.name}'.")

        # Criar canal de verificação
        verification_cat = self.bot.get_channel(VERIFICATION_CATEGORY_ID)
        if not verification_cat:
            print(f"[ERRO] Categoria ID={VERIFICATION_CATEGORY_ID} não encontrada.")
            return
        if not isinstance(verification_cat, discord.CategoryChannel):
            print(f"[ERRO] Objeto ID={VERIFICATION_CATEGORY_ID} não é CategoryChannel.")
            return

        channel_name = f"verificacao-{member.name.lower().replace(' ', '-')}"
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            self.bot.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        try:
            verification_channel = await verification_cat.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason="Canal temporário de verificação"
            )
            self.verification_channels[member.id] = verification_channel.id
            print(f"[DEBUG] Canal de verificação criado: {verification_channel.name} (ID={verification_channel.id}) para {member}.")

            msg_intro = (
                f"Olá {member.mention}!\n"
                "Bem-vindo ao servidor. Antes de participar, preciso do seu **nome no jogo**.\n\n"
                f"Digite aqui seu nome no jogo dentro de {VERIFICATION_TIMEOUT//60} minutos. "
                "Depois disso, este canal será removido!"
            )
            await verification_channel.send(msg_intro)

            # Esperar a resposta do usuário
            await self.aguardar_resposta(member, verification_channel)

        except Exception as e:
            print(f"[ERRO] ao criar canal de verificação para {member}: {e}")

    async def aguardar_resposta(self, member: discord.Member, channel: discord.TextChannel):
        """
        Espera a mensagem do usuário no canal 'channel'.
        Se o tempo expirar, deleta o canal.
        Se chegar, define apelido, salva no DB e remove cargo.
        """
        def check(m: discord.Message):
            return m.channel.id == channel.id and m.author.id == member.id

        try:
            resposta = await self.bot.wait_for("message", timeout=VERIFICATION_TIMEOUT, check=check)
        except asyncio.TimeoutError:
            print(f"[DEBUG] Tempo esgotado para {member}, canal {channel.name}. Excluindo canal.")
            await channel.send("Tempo esgotado! Você não forneceu seu nome. Este canal será excluído.")
            await asyncio.sleep(5)
            await channel.delete(reason="Tempo de verificação esgotado.")
            return

        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        print(f"[DEBUG] {member} informou nome no jogo: '{in_game_name}'. Tentando editar apelido para '{novo_nick}'.")

        # Tenta editar o apelido
        try:
            await member.edit(nick=novo_nick)
            print(f"[DEBUG] Apelido de {member} alterado para '{novo_nick}'.")
        except discord.Forbidden:
            await channel.send("Não tenho permissão para alterar seu apelido. Contate um administrador!")
            print(f"[ERRO] Permissão negada para editar apelido de {member}.")
            return
        except Exception as e:
            print(f"[ERRO] ao editar apelido de {member}: {e}")
            return

        # Salva no DB
        self.salvar_in_game_name(member.id, in_game_name)

        # Remove cargo "Aguardando Verificação"
        role = member.guild.get_role(ROLE_AGUARDANDO_ID)
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Usuário verificado com sucesso.")
                print(f"[DEBUG] Removido cargo '{role.name}' de {member}.")
            except discord.Forbidden:
                print(f"[ERRO] Permissão negada para remover cargo '{role.name}' de {member}.")
            except Exception as e:
                print(f"[ERRO] ao remover cargo '{role.name}': {e}")

        await channel.send(
            f"✅ Obrigado, {member.mention}! Seu apelido foi atualizado para `{novo_nick}`.\n"
            "Você já pode participar do servidor. Apagaremos este canal em 5 segundos..."
        )
        await asyncio.sleep(5)
        try:
            await channel.delete(reason="Verificação concluída.")
            print(f"[DEBUG] Canal {channel.name} excluído após verificação de {member}.")
        except Exception as e:
            print(f"[ERRO] ao deletar canal {channel.name}: {e}")

        # Remover do dicionário
        self.verification_channels.pop(member.id, None)

        # Log de verificação
        await self.logar(f"O usuário {member} foi verificado como '{in_game_name}'. Canal '{channel.name}' removido.")

    def salvar_in_game_name(self, discord_id: int, in_game_name: str):
        """
        Salva ou atualiza o nome no jogo no DB.
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
            print(f"[DEBUG] Nome no jogo '{in_game_name}' salvo para ID={discord_id} no banco.")
        except Exception as e:
            session.rollback()
            print(f"[ERRO DB] Não foi possível salvar: {e}")
        finally:
            session.close()

    async def logar(self, mensagem: str):
        """
        Envia logs para o canal staff, se configurado.
        """
        if LOG_CHANNEL_ID:
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if channel:
                try:
                    await channel.send(mensagem)
                except discord.Forbidden:
                    print(f"[ERRO] Não tenho permissão de enviar mensagem em {channel}.")

async def setup(bot: commands.Bot):
    # Adiciona este cog ao bot.
    await bot.add_cog(NomeCog(bot))
