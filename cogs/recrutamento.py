import discord
from discord.ext import commands
import asyncio

class RecrutamentoCog(commands.Cog):
    """
    Cog para processar recrutamento e procura de clã.
    - Formato válido: NomeJogador, NomeClã, recrutando
                    ou NomeJogador, NomeClã, procurando
    - Qualquer outra mensagem é apagada e um tutorial aparece por 30s.
    """

    CHECK_EMOJI = "✅"
    CROSS_EMOJI = "❌"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora bots e DMs
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        parts = [p.strip() for p in content.split(',')]

        # Se for formato válido, cria embed de recrutamento/procura
        if len(parts) == 3 and parts[2].lower() in ("recrutando", "procurando"):
            nome_jogo, nome_clan, acao = parts
            acao_lower = acao.lower()

            titulo = "Recrutamento de Clã" if acao_lower == "recrutando" else "Procura de Clã"
            embed = discord.Embed(title=titulo, color=discord.Color.blue())
            embed.add_field(name="Jogador (Discord)", value=message.author.mention, inline=False)
            embed.add_field(name="Nome no jogo",     value=nome_jogo,          inline=True)
            embed.add_field(name="Clã",             value=nome_clan,          inline=True)
            embed.add_field(name="Status",          value=acao.capitalize(),  inline=False)
            embed.set_footer(text="Reaja ✅ ou ❌ para entrar em contato.")

            # Apaga mensagem original
            try:
                await message.delete()
            except:
                pass

            # Envia embed e adiciona reações
            novo_msg = await message.channel.send(embed=embed)
            await novo_msg.add_reaction(self.CHECK_EMOJI)
            await novo_msg.add_reaction(self.CROSS_EMOJI)
            return

        # Qualquer outra mensagem: apaga e envia tutorial
        try:
            await message.delete()
        except:
            pass

        tutorial = discord.Embed(
            title="Como usar Recrutamento/Procura de Clã",
            description=(
                "Envie uma mensagem exatamente neste formato:\n\n"
                "`NomeJogador, NomeClã, recrutando`\n"
                "ou\n"
                "`NomeJogador, NomeClã, procurando`\n\n"
                "Exemplo:\n"
                "`Fulano123, OrdemDosHeróis, recrutando`"
            ),
            color=discord.Color.gold()
        )
        tutorial_msg = await message.channel.send(embed=tutorial)

        # Mantém o tutorial por 30 segundos e depois apaga
        await asyncio.sleep(30)
        try:
            await tutorial_msg.delete()
        except:
            pass

    async def cog_load(self):
        # Opcional: print no console quando o cog for carregado
        print(f"{self.__class__.__name__} carregado.")

async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutamentoCog(bot))
