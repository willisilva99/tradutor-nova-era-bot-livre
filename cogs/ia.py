# cogs/ia.py  – versão enxuta com prompt especializado

import os, time, asyncio
from typing import Dict
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()

API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

SERVER_NAME = "Anarquia Z"

SYSTEM_PROMPT = f"""
Você é a assistente oficial do servidor {SERVER_NAME}.
Especialidades:
• 7 Days to Die – mecânicas, receitas, hordas, dicas de construção, mods.
• Conan Exiles – atributos, religiões, chefes, PvP, construção e administração de servidores.
Regras:
1. Responda somente sobre esses dois jogos.
2. Se a pergunta fugir do tema, recuse educadamente indicando os jogos suportados.
3. Quando apropriado, mencione que a comunidade joga no servidor {SERVER_NAME}.
4. Use português brasileiro, seja objetivo e amigável.
"""

COOLDOWN_SECONDS = 60

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_answer: Dict[int, float] = {}

    # ─ utilidades ─
    @staticmethod
    def _looks_like_question(text: str) -> bool:
        text = text.lower()
        return "?" in text or any(k in text for k in ("como ", "how ", "help", "ajuda", "dúvida"))

    async def _chat(self, q: str) -> str:
        try:
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": q},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except OpenAIError as e:
            print("[IA] Erro:", e)
            return "Desculpe, houve um problema ao consultar a IA."

    # ─ listener ─
    @commands.Cog.listener("on_message")
    async def auto_helper(self, msg: discord.Message):
        if msg.author.bot or not self._looks_like_question(msg.content):
            return
        if time.time() - self.last_answer.get(msg.channel.id, 0) < COOLDOWN_SECONDS:
            return
        await msg.reply(await self._chat(msg.content), mention_author=False)
        self.last_answer[msg.channel.id] = time.time()

    # ─ slash ─
    @app_commands.command(name="ia", description="Pergunte algo sobre 7DTD ou Conan Exiles")
    @app_commands.describe(pergunta="Sua dúvida")
    async def ia_slash(self, itx: discord.Interaction, pergunta: str):
        await itx.response.defer(thinking=True, ephemeral=True)
        await itx.followup.send(await self._chat(pergunta), ephemeral=True)

    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ia_ping(self, itx: discord.Interaction):
        t0 = time.perf_counter(); _ = await self._chat("Diga apenas 'pong'.")
        await itx.response.send_message(f"🏓 IA Pong! {int((time.perf_counter()-t0)*1000)} ms")

async def setup(bot): await bot.add_cog(IACog(bot))
