# ia.py  (coloque em ./cogs)

import os
import re
import time
import asyncio
from typing import Dict

import discord
from discord.ext import commands
from discord import app_commands

from dotenv import load_dotenv
import openai

# ───────────────────────────────────────
# Carrega variáveis de ambiente do .env
# (no Hawaii você define no painel; localmente basta criar .env)
# ───────────────────────────────────────
load_dotenv()

openai.api_key  = os.getenv("OPENAI_API_KEY")
openai.base_url = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")

# Mensagem de sistema fixa p/ limitar a IA a 7DTD
SYSTEM_PROMPT = (
    "Você é uma inteligência artificial especialista SOMENTE em 7 Days to Die. "
    "Responda unicamente sobre o jogo; se a pergunta fugir do tema, peça desculpas "
    "e diga que não pode ajudar."
)

# Cool-down para evitar spam automático (por canal)
COOLDOWN_SECONDS = 60


class IACog(commands.Cog):
    """
    Cog que injeta uma IA gratuita (OpenAI-compatible) focada em 7 Days to Die.
    - Slash-command /ia  → resposta direta
    - Escuta mensagens e, se detectar dúvida, responde automaticamente com limite de flood
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_answer: Dict[int, float] = {}   # canal_id → timestamp

    # ──────────────── Utilidades ────────────────
    @staticmethod
    def _looks_like_question(text: str) -> bool:
        """Heurística bem simples para detectar dúvidas."""
        text = text.lower()
        return "?" in text or any(
            kw in text
            for kw in ("como ", "ajuda", "help", "dúvida", "how ")
        )

    async def _chat_completion(self, user_question: str) -> str:
        """
        Consulta o modelo escolhido no servidor OpenAI-compatible indicado por
        OPENAI_API_BASE.  Mantém temperatura baixa para respostas objetivas.
        """
        try:
            response = await asyncio.to_thread(
                openai.chat.completions.create,
                model="mistral-7b-instruct",   # troque para qualquer modelo habilitado
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_question},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[IA] Erro ao chamar LLM: {exc}")
            return "Desculpe, houve um problema ao consultar a IA."

    # ─────────────── Listener automático ───────────────
    @commands.Cog.listener("on_message")
    async def auto_helper(self, message: discord.Message):
        if message.author.bot:
            return  # ignora bots, inclusive ele mesmo

        # Detecta se parece dúvida
        if not self._looks_like_question(message.content):
            return

        now = time.time()
        last = self.last_answer.get(message.channel.id, 0)
        if now - last < COOLDOWN_SECONDS:
            return  # evita flood

        answer = await self._chat_completion(message.content)
        await message.reply(answer, mention_author=False)
        self.last_answer[message.channel.id] = now

    # ─────────────── Slash-command explícito ───────────────
    @app_commands.command(
        name="ia",
        description="Faça uma pergunta sobre 7 Days to Die (IA gratuita)",
    )
    @app_commands.describe(pergunta="Sua dúvida")
    async def ia_slash(self, interaction: discord.Interaction, pergunta: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        answer = await self._chat_completion(pergunta)
        await interaction.followup.send(answer, ephemeral=True)

    # Opcional: ping para ver se a IA está ok
    @app_commands.command(name="ia_ping", description="Latência com o modelo de IA")
    async def ia_ping(self, interaction: discord.Interaction):
        before = time.perf_counter()
        _ = await self._chat_completion("Diga apenas 'pong'.")
        latency_ms = int((time.perf_counter() - before) * 1000)
        await interaction.response.send_message(f"🏓 IA Pong! {latency_ms} ms")

# ─────────────── Carregamento pelo bot ───────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(IACog(bot))
