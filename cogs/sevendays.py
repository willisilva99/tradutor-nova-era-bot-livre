# cogs/sevendays.py

import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.orm import Session
import asyncio

from db import SessionLocal, ServerConfig

# Supondo que já existam:
# active_connections = {}
# class TelnetConnection: ...

class SevenDaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ... seus outros comandos (addserver, channel, test, etc.) ...

    @app_commands.command(name="7dtd_bloodmoon", description="Mostra quando ocorre a próxima lua de sangue.")
    async def bloodmoon_status(self, interaction: discord.Interaction):
        """
        Exemplo:
        - Chama "gettime" no servidor
        - Faz parse de algo tipo "Day 14, 12:34"
        - Computa quanta hora/dia falta até a lua de sangue
        - Exibe resultado
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)

        # Certifica-se de ter a conexão em active_connections
        # (ou tente recriar do DB se não existir, caso use esse padrão)
        if guild_id not in active_connections:
            # Tenta recriar do DB
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                    return
                from cogs.sevendays import TelnetConnection
                conn = TelnetConnection(
                    guild_id=guild_id,
                    ip=cfg.ip,
                    port=cfg.port,
                    password=cfg.password,
                    channel_id=cfg.channel_id,
                    bot=self.bot
                )
                active_connections[guild_id] = conn
                conn.start()

        conn = active_connections[guild_id]

        # Comando "gettime"
        try:
            response = await conn.send_command("gettime")
        except Exception as e:
            await interaction.followup.send(f"Erro ao obter horário do servidor: {e}", ephemeral=True)
            return

        # Normalmente, se o servidor retorna algo como "Day 14, 12:34"
        # Precisamos fazer parse.
        day = None
        hour = None
        minute = 0
        lines = response.splitlines()
        for line in lines:
            line = line.strip()
            # Ex: "Day 14, 12:34"
            if line.startswith("Day "):
                # Tenta extrair "14" e "12:34"
                # Formato exato pode variar; ajuste se necessário.
                # Ex: "Day 14, 12:34"
                parts = line.replace("Day ", "").split(",")  # ["14", "12:34"]
                if len(parts) == 2:
                    try:
                        day_str = parts[0].strip()
                        time_str = parts[1].strip()  # "12:34"
                        day = int(day_str)
                        # Agora separa hour:minute
                        hm = time_str.split(":")
                        if len(hm) == 2:
                            hour = int(hm[0])
                            minute = int(hm[1])
                    except:
                        pass

        if day is None or hour is None:
            # Não achamos um valor parseável
            await interaction.followup.send(
                f"Não foi possível parsear o horário no output:\n```\n{response}\n```",
                ephemeral=True
            )
            return

        # Supondo horda a cada 7 dias
        # A horda acontece no dia divisível por 7, a partir das 22h até ~4h
        # Exemplo simples:
        horde_freq = 7

        # Verifica se hoje é dia de horda
        daysFromHorde = day % horde_freq  # resto
        # Se daysFromHorde == 0 => dia de horda
        # Horda começa ~22h e vai até ~4h do dia seguinte

        # Monta mensagem
        message = f"Hoje é **Dia {day}, {hour:02d}:{minute:02d}** no servidor."

        # Lógica rápida:
        if daysFromHorde == 0:
            # É dia de horda
            if hour >= 22 or hour < 4:
                message += "\n**A horda está acontecendo agora!**"
            elif hour < 22:
                hrs_left = 22 - hour
                message += f"\n**A horda começa em {hrs_left} hora(s).**"
            else:
                # passou das 4h do dia do horde => a horda acabou
                # e a próxima deve ser no dia + 7
                next_day = day + 7
                message += f"\nA horda de hoje já passou! Próxima no **Dia {next_day}**."
        else:
            # não é dia de horda
            # quantos dias faltam
            days_to_horde = horde_freq - daysFromHorde
            next_horde_day = day + days_to_horde
            message += f"\nPróxima lua de sangue no **Dia {next_horde_day}** (em {days_to_horde} dia(s))."

        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(name="7dtd_players", description="Lista quantos/quais jogadores estão online no 7DTD.")
    async def players_online(self, interaction: discord.Interaction):
        """
        Exemplo:
        - Chama "lp" no servidor
        - Tenta parsear algo como:
            "Total of 3 in the game"
            "EntityID   PlayerName ..."
            ...
        - Monta embed com a lista
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = str(interaction.guild_id)

        if guild_id not in active_connections:
            with SessionLocal() as session:
                cfg = session.query(ServerConfig).filter_by(guild_id=guild_id).first()
                if not cfg:
                    await interaction.followup.send("Nenhum servidor configurado. Use /7dtd_addserver primeiro.", ephemeral=True)
                    return
                from cogs.sevendays import TelnetConnection
                conn = TelnetConnection(
                    guild_id=guild_id,
                    ip=cfg.ip,
                    port=cfg.port,
                    password=cfg.password,
                    channel_id=cfg.channel_id,
                    bot=self.bot
                )
                active_connections[guild_id] = conn
                conn.start()

        conn = active_connections[guild_id]

        try:
            response = await conn.send_command("lp")
        except Exception as e:
            await interaction.followup.send(f"Erro ao executar comando lp: {e}", ephemeral=True)
            return

        # Exemplo de resposta:
        # Total of 3 in the game
        # EntityID    PlayerName ...
        # 178         John ...
        # 101         Mary ...
        # 13          Bob ...
        lines = response.splitlines()
        player_names = []
        total_msg = None

        for line in lines:
            line = line.strip()
            if line.startswith("Total of "):
                total_msg = line  # Ex: "Total of 3 in the game"
            elif "EntityID" in line:
                # cabeçalho, ignora
                pass
            else:
                # pode ser um player. Ex:
                # "178 John <SteamId> ..."
                # Vamos pegar a 2ª coluna como nome,
                # mas real parse depende do layout
                parts = line.split()
                if len(parts) >= 2:
                    # parts[0] = entityID, parts[1] = nome
                    name = parts[1]
                    # Se for algo sem
                    if name not in ("SteamID", "PlayerName"):
                        player_names.append(name)

        # Monta a mensagem final
        if total_msg is None:
            # sem info de total?
            total_msg = "Não encontrei quantidade total de players."

        if player_names:
            players_str = ", ".join(player_names)
        else:
            players_str = "Nenhum player listado."

        embed = discord.Embed(
            title="Jogadores Online",
            description=(
                f"{total_msg}\n\n"
                f"**Lista**: {players_str}"
            ),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SevenDaysCog(bot))
