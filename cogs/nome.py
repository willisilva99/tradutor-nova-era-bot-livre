import re
import discord
from discord.ext import commands
import asyncio

# Para slash commands no discord.py 2.0, usamos 'app_commands'
from discord import app_commands

from db import SessionLocal, PlayerName  # Ajuste se o modelo PlayerName estiver em outro arquivo

# ID do canal de logs (opcional). Se não usar logs, pode remover.
LOG_CHANNEL_ID = 978460787586789406

class NomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Regex para checar formato: [nome] - nome
        self.pattern = re.compile(r'^\[.+\]\s*-\s*.+$')
        self.verificados = set()  # Cache local
        self.currently_restoring = set()  # Evitar loop ao restaurar apelido

    # ====================================================
    # 1) Slash Command usando app_commands
    # ====================================================
    @app_commands.command(name="setnome", description="Defina ou atualize seu nome no jogo.")
    async def set_nome(self, interaction: discord.Interaction, nome_do_jogo: str):
        """
        Permite que o usuário ajuste manualmente seu [NomeDoJogo] - NomeDiscord.
        Com o 'app_commands.command', este é um slash command.
        """
        member = interaction.user
        if member.bot:
            await interaction.response.send_message("Bots não precisam de apelido!", ephemeral=True)
            return

        novo_nick = f"[{nome_do_jogo}] - {member.name}"
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar seu apelido. Verifique se meu cargo está acima do seu!",
                ephemeral=True
            )
            return

        # Salvar no banco
        self.salvar_in_game_name(member.id, nome_do_jogo)
        # Adicionar ao cache
        self.verificados.add(member.id)

        # Resposta no canal de slash (geralmente ephemeral)
        await interaction.response.send_message(
            f"Apelido atualizado para `{novo_nick}` com sucesso!",
            ephemeral=True
        )

        # Log opcional
        await self.logar(f"**/setnome** usado por {member.mention}: agora é `{novo_nick}`.")

    # ====================================================
    # 2) Quando um membro entra, verificar apelido
    # ====================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        if member.nick and self.pattern.match(member.nick):
            self.verificados.add(member.id)
        else:
            await self.solicitar_nome_jogo(member)

    # ====================================================
    # 3) Detectar mudança de apelido e manter formato
    # ====================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot or after.bot:
            return

        if before.nick == after.nick:
            return  # não mudou nada

        # Se já estamos restaurando, não faz nada
        if after.id in self.currently_restoring:
            return

        # Se o novo apelido ainda combina com o padrão, marca como verificado
        if after.nick and self.pattern.match(after.nick):
            self.verificados.add(after.id)
        else:
            # Avisar via DM
            try:
                await after.send(
                    "⚠️ Você alterou seu apelido e ele não está mais no formato "
                    "`[NomeDoJogo] - NomeDiscord`. Por favor, mantenha o formato correto."
                )
            except discord.Forbidden:
                pass

            await self.logar(
                f"{after.mention} removeu o formato do apelido. Antes: `{before.nick}`, depois: `{after.nick}`"
            )

            # Se quiser forçar a restauração (cuidado com loop infinito):
            if before.nick and self.pattern.match(before.nick):
                self.currently_restoring.add(after.id)
                try:
                    await after.edit(nick=before.nick)
                except discord.Forbidden:
                    pass
                self.currently_restoring.remove(after.id)

    # ====================================================
    # 4) on_message otimizado com cache
    # ====================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return

        member = message.author

        # Se já está verificado no cache, não precisa checar
        if member.id in self.verificados:
            return

        # Caso contrário, checa se o apelido confere. Se sim, marca verificado
        if member.nick and self.pattern.match(member.nick):
            self.verificados.add(member.id)
        else:
            # Apaga a mensagem e avisa
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # Tenta mandar DM
            dm_enviado = await self.tentar_enviar_dm(member)
            if dm_enviado:
                await self.logar(f"Mensagem de {member.mention} apagada (apelido fora do formato).")
            else:
                await self.logar(
                    f"Não pude mandar DM para {member.mention}. Mensagem apagada (apelido fora do formato)."
                )

    # ====================================================
    # 5) Perguntar nome do jogo (DM)
    # ====================================================
    async def solicitar_nome_jogo(self, member: discord.Member):
        try:
            dm_channel = await member.create_dm()
            await dm_channel.send(
                "Olá! Percebi que você não está com seu apelido no formato `[NomeDoJogo] - NomeDiscord`.\n"
                "Por favor, me diga agora: **qual é seu nome no jogo?**"
            )
        except discord.Forbidden:
            await self.logar(f"Não pude DM {member.mention} (verificação de apelido falhou).")
            return

        def check(m: discord.Message):
            return m.author == member and m.channel == dm_channel

        try:
            resposta = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await dm_channel.send("Você não respondeu a tempo. Tente novamente mais tarde!")
            return

        in_game_name = resposta.content.strip()
        novo_nick = f"[{in_game_name}] - {member.name}"

        # Tenta editar o apelido
        try:
            await member.edit(nick=novo_nick)
        except discord.Forbidden:
            await dm_channel.send("Não tenho permissão para alterar seu apelido. Contate um administrador!")
            return

        # Salva no banco e marca como verificado
        self.salvar_in_game_name(member.id, in_game_name)
        self.verificados.add(member.id)

        await dm_channel.send(f"✅ Seu apelido foi atualizado para `{novo_nick}`. Obrigado!")
        await self.logar(f"{member.mention} teve o apelido configurado para `{novo_nick}`.")

    # ====================================================
    # 6) Auxiliar: enviar DM pedindo pra definir apelido
    # ====================================================
    async def tentar_enviar_dm(self, member: discord.Member) -> bool:
        try:
            dm_channel = await member.create_dm()
            await dm_channel.send(
                "❌ Você não pode enviar mensagens no servidor sem definir seu apelido "
                "no formato `[NomeDoJogo] - NomeDiscord`.\n\n"
                "Qual é seu nome no jogo?"
            )
            return True
        except discord.Forbidden:
            return False

    # ====================================================
    # 7) Salvar no banco de dados
    # ====================================================
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

    # ====================================================
    # 8) Logar ações em canal staff
    # ====================================================
    async def logar(self, mensagem: str):
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel is not None:
            try:
                await channel.send(mensagem)
            except discord.Forbidden:
                pass

async def setup(bot: commands.Bot):
    # Adiciona a Cog
    await bot.add_cog(NomeCog(bot))
    # Opcional: Se quiser forçar sincronizar
    # try:
    #     synced = await bot.tree.sync()
    #     print(f"Slash commands sincronizados! ({len(synced)}) comandos.")
    # except Exception as e:
    #     print(f"Erro ao sincronizar slash commands: {e}")
