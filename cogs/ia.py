# cogs/ia.py
# IA especialista em 7 Days to Die — compatível com DeepInfra (OpenAI-compatible)

import os
import time
import asyncio
from typing import Dict

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError      # SDK 1.x+

# ───────────────────────────────
# Variáveis de ambiente (.env ou Railway)
# ───────────────────────────────
load_dotenv()

API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")          # ex.: di_abcd1234…
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

EXTRA_HEADERS = {}            # DeepInfra não exige cabeçalhos extras
SYSTEM_PROMPT = (
    "Você é uma inteligência artificial especialista SOMENTE em 7 Days to Die. "
    "Responda unicamente sobre o jogo; se a pergunta fugir do tema, peça desculpas "
    "e diga que não pode ajudar."
)
COOLDOWN_SECONDS = 60         # flood-control por canal

# ───────────────────────────────
class IACog(commands.Cog):
    """Cog que injeta IA gratuita (DeepInfra) focada em 7DTD."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_answer: Dict[int, float] = {}

    # ───────── utilidades ─────────
    @staticmethod
    def _looks_like_question(text: str) -> bool:
        text = text.lower()
        return "?" in text or any(
            kw in text for kw in ("como ", "how ", "help", "ajuda", "dúvida")
        )

    async def _chat_completion(self, question: str) -> str:
        try:
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": question},
                ],
                max_tokens=512,
                temperature=0.3,
                extra_headers=EXTRA_HEADERS,
            )
            return resp.choices[0].message.content.strip()
        except OpenAIError as exc:
            print(f"[IA] Erro no LLM: {exc}")
            return "Desculpe, houve um problema ao consultar a IA."

    # ─────── listener automático ───────
    @commands.Cog.listener("on_message")
    async def auto_helper(self, message: discord.Message):
        if message.author.bot or not self._looks_like_question(message.content):
            return

        now = time.time()
        if now - self.last_answer.get(message.channel.id, 0) < COOLDOWN_SECONDS:
            return

        answer = await self._chat_completion(message.content)
        await message.reply(answer, mention_author=False)
        self.last_answer[message.channel.id] = now

    # ─────── slash-commands ───────
    @app_commands.command(name="ia", description="Pergunte algo sobre 7 Days to Die")
    @app_commands.describe(pergunta="Sua dúvida")
    async def ia_slash(self, interaction: discord.Interaction, pergunta: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        answer = await self._chat_completion(pergunta)
        await interaction.followup.send(answer, ephemeral=True)

    @app_commands.command(name="ia_ping", description="Latência com o modelo de IA")
    async def ia_ping(self, interaction: discord.Interaction):
        before = time.perf_counter()
        _ = await self._chat_completion("Diga apenas 'pong'.")
        latency_ms = int((time.perf_counter() - before) * 1000)
        await interaction.response.send_message(f"🏓 IA Pong! {latency_ms} ms")

# ───────── carregamento ─────────
async def setup(bot: commands.Bot):
    await bot.add_cog(IACog(bot))
