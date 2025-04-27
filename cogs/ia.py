# cogs/ia.py
# IA focada em 7 Days to Die – usando a nova classe OpenAI() do SDK 1.x

import os
import time
import asyncio
from typing import Dict

import discord
from discord.ext import commands
from discord import app_commands

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError   # novo client

# ───────────────────────────────
# Variáveis de ambiente
# ───────────────────────────────
load_dotenv()

API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
API_KEY  = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido no ambiente!")

client = OpenAI(
    base_url=API_BASE,
    api_key=API_KEY,
)

EXTRA_HEADERS = {}
if ref := os.getenv("OPENAI_REFERER"):
    EXTRA_HEADERS["HTTP-Referer"] = ref
if title := os.getenv("OPENAI_SITE_TITLE"):
    EXTRA_HEADERS["X-Title"] = title

SYSTEM_PROMPT = (
    "Você é uma inteligência artificial especialista SOMENTE em 7 Days to Die. "
    "Responda unicamente sobre o jogo; se a pergunta fugir do tema, peça desculpas "
    "e diga que não pode ajudar."
)

MODEL_NAME = os.getenv("OPENAI_MODEL", "mistralai/mistral-7b-instruct-v0.2")
COOLDOWN_SECONDS = 60   # flood-control por canal


class IACog(commands.Cog):
    """Cog que injeta IA (OpenRouter / OpenAI-compatible) focada em 7DTD."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_answer: Dict[int, float] = {}   # canal_id → timestamp

    # ─────────────────── utilidades ───────────────────
    @staticmethod
    def _looks_like_question(text: str) -> bool:
        text = text.lower()
        return "?" in text or any(
            kw in text for kw in ("como ", "ajuda", "help", "dúvida", "how ")
        )

    async def _chat_completion(self, user_question: str) -> str:
        """Envia a pergunta ao modelo."""
        try:
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_question},
                ],
                extra_headers=EXTRA_HEADERS,
                temperature=0.3,
                max_tokens=512,
            )
            return resp.choices[0].message.content.strip()
        except OpenAIError as exc:
            print(f"[IA] Erro no LLM: {exc}")
            return "Desculpe, houve um problema ao consultar a IA."

    # ─────────────────── listener automático ───────────────────
    @commands.Cog.listener("on_message")
    async def auto_helper(self, message: discord.Message):
        if message.author.bot:
            return
        if not self._looks_like_question(message.content):
            return

        now = time.time()
        if now - self.last_answer.get(message.channel.id, 0) < COOLDOWN_SECONDS:
            return

        answer = await self._chat_completion(message.content)
        await message.reply(answer, mention_author=False)
        self.last_answer[message.channel.id] = now

    # ─────────────────── slash-commands ───────────────────
    @app_commands.command(
        name="ia",
        description="Pergunte algo sobre 7 Days to Die (IA)"
    )
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

# ─────────────────── carregamento ───────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(IACog(bot))
