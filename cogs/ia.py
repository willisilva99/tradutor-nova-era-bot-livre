# cogs/ia.py – IA + RAG + Streaming + Cache(DB) + Cooldown + /doc (2025-04-26)

import os, re, time, asyncio, textwrap
from datetime import datetime
from typing import Dict, List, Tuple

import aiohttp
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
from discord import app_commands

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
from openai import OpenAI, OpenAIError
from cachetools import TTLCache
from langdetect import detect
from tqdm.asyncio import tqdm_asyncio

# Importa cache persistente em banco e função normalize
from sqlalchemy.exc import SQLAlchemyError
from db import SessionLocal, AICache, normalize

# ─────────────────────────── Configurações básicas
load_dotenv()
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
OWNER_ID = 470628393272999948
SERVER   = "Anarquia Z"

# Fontes para RAG
LINKS = [
    "https://anarquia-z.netlify.app",
    "https://conan-exiles.com/server/91181/",
    "https://7daystodie-servers.com/server/151960/",
    "https://7daystodie.com/v2-0-storms-brewing-status-update/",
    "https://7daystodie.fandom.com/wiki/Beginners_Guide",
    "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "https://7daystodie.fandom.com/wiki/List_of_Zombies",
    "https://www.ign.com/wikis/7-days-to-die/Zombies_List",
    "https://ultahost.com/blog/pt/top-5-piores-perks-em-7-days-to-die/",
    "https://www.reddit.com/r/7daystodie/comments/p3ek6y/help_with_skills/?tl=pt-br",
    "https://r.jina.ai/http://x.com/7daystodie",
]

# Atalhos /doc
DOCS = {
    "forja": "https://7daystodie.fandom.com/wiki/Forging_System",
    "blood moon": "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "zumbis": "https://7daystodie.fandom.com/wiki/List_of_Zombies",
}

# Checa chave da API
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

# Inicializa cliente e vetores RAG
client   = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=30)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
chroma   = chromadb.PersistentClient(path="chromadb")
col      = chroma.get_or_create_collection("anarquia_z_rag")

# ─────────────────────────── Prompts base
PROMPT_PT = textwrap.dedent(f"""
    Olá! Eu sou a <Assistente Z> 🤖 do servidor **{SERVER}**.
    • Especialista em 7 Days to Die 🔨 e Conan Exiles 🗡️
    • Se perguntarem quem é o dono, responda <@{OWNER_ID}>.
    • Quando fizer sentido, convide o jogador a entrar no **{SERVER}**.
    Responda em português brasileiro, de forma acolhedora, clara e use emojis.
""" )

PROMPT_EN = textwrap.dedent(f"""
    Hi! I'm <Assistant Z> 🤖 from **{SERVER}** community.
    • I only cover 7 Days to Die 🔨 and Conan Exiles 🗡️.
    • The server owner is <@{OWNER_ID}>.
    • Feel free to join **{SERVER}** anytime!
    Answer in friendly and concise English, using emojis when it fits.
""" )

# ─────────────────────────── Cache e Timeout
CACHE_TTL = TTLCache(maxsize=2048, ttl=43200)  # 12h cache rápido
COOLDOWN  = 60  # cooldown por usuário (s)
MAX_LEN   = 4000

# ─────────────────────────── Funções de cache em DB

def db_get_cached(raw_question: str) -> str | None:
    key = normalize(raw_question)
    with SessionLocal() as db:
        row = db.query(AICache).filter_by(question=key).first()
        return row.answer if row else None


def db_set_cached(raw_question: str, answer: str):
    key = normalize(raw_question)
    with SessionLocal() as db:
        try:
            row = db.query(AICache).filter_by(question=key).first()
            if row:
                row.answer     = answer
                row.updated_at = datetime.utcnow()
            else:
                db.add(AICache(question=key, answer=answer))
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            print("[AI-Cache] ERRO:", e)

# ─────────────────────────── Helpers RAG

def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _chunk(text: str, size: int = 500) -> List[str]:
    words = text.split()
    return [" ".join(words[i:i+size]) for i in range(0, len(words), size)]

async def _download(session, url: str) -> str:
    try:
        async with session.get(url, timeout=30) as r:
            return await r.text()
    except Exception as e:
        print(f"[RAG] Falhou {url[:60]}… {e}")
        return ""

async def build_vector_db():
    if col.count():
        return
    print("[RAG] Construindo base…")
    headers = {"User-Agent": "Mozilla/5.0 (RAG-Bot)"}
    async with aiohttp.ClientSession(headers=headers) as sess:
        pages = await tqdm_asyncio.gather(*[_download(sess, u) for u in LINKS])
    for url, html in zip(LINKS, pages):
        txt = _clean(html)
        for i, chunk in enumerate(_chunk(txt)):
            col.add(
                ids=[f"{url}#{i}"],
                documents=[chunk],
                embeddings=[embedder.encode(chunk).tolist()]
            )
        print(f"[RAG] {url} ➜ {len(txt)//1000}k chars")


def retrieve_ctx(question: str, k: int = 5) -> str:
    if not col.count():
        return ""
    vec = embedder.encode(question).tolist()
    res = col.query([vec], n_results=k, include=["documents"])
    return "\n---\n".join(res["documents"][0])

# ─────────────────────────── Cog principal

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot  = bot
        self.last: Dict[Tuple[int,int], float] = {}

    async def cog_load(self):
        asyncio.create_task(build_vector_db())
        self.refresh_embeddings.start()

    @tasks.loop(hours=24)
    async def refresh_embeddings(self):
        col.delete_collection()
        await build_vector_db()

    async def _chat_stream(self, prompt: str, lang: str):
        # 1) Cache DB
        cached_db = db_get_cached(prompt)
        if cached_db:
            yield cached_db
            return
        # 2) Cache rápido
        key = normalize(prompt)
        if key in CACHE_TTL:
            yield CACHE_TTL[key]
            return
        # 3) Geração via API
        sys_prompt = PROMPT_EN if lang == "en" else PROMPT_PT
        ctx        = retrieve_ctx(prompt)
        msgs       = [
            {"role": "system", "content": sys_prompt},
            {"role": "system", "content": f"Contexto:\n{ctx}"},
            {"role": "user",   "content": prompt},
        ]
        full_text = ""
        response  = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_ID, messages=msgs,
            temperature=0.5, max_tokens=512, stream=True
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            full_text += delta.content or ""
            yield full_text
        # 4) Grava cache
        db_set_cached(prompt, full_text)
        CACHE_TTL[key] = full_text

    async def _stream_to_channel(self, ch, prompt: str, ref=None, itx=None, eph=False):
        lang = 'en' if detect(prompt) == 'en' else 'pt'
        # Mensagem inicial
        if itx:
            await itx.edit_original_response(content="⌛ Pensando…")
        else:
            thinking = await ch.send("⌛ Pensando…", reference=ref)
        # Streaming e coleta final
        final_text = ""
        async for partial in self._chat_stream(prompt, lang):
            final_text = partial
            snippet    = final_text[-MAX_LEN:]
            try:
                if itx:
                    await itx.edit_original_response(content=snippet)
                else:
                    await thinking.edit(content=snippet)
            except discord.HTTPException:
                pass
        # Embed final
        embed = discord.Embed(
            description=final_text,
            color=COLOR,
            title=f"{ICON} Resposta"
        )
        embed.set_footer(text=f"Assistente • {SERVER}")
        if itx:
            await itx.edit_original_response(content=None, embed=embed)
        else:
            await thinking.edit(content=None, embed=embed)

    @commands.Cog.listener("on_message")
    async def auto(self, msg: discord.Message):
        if msg.author.bot or '?' not in msg.content:
            return
        key = (msg.channel.id, msg.author.id)
        if time.time() - self.last.get(key, 0) < COOLDOWN:
            return
        await self._stream_to_channel(msg.channel, msg.content, ref=msg)
        self.last[key] = time.time()

    @app_commands.command(name="ia", description="Pergunte algo sobre 7DTD / Conan")
    @app_commands.describe(pergunta="Sua dúvida")
    async def ia(self, itx: discord.Interaction, pergunta: str):
        await itx.response.defer(ephemeral=True)
        await self._stream_to_channel(itx.channel, pergunta, itx=itx, eph=True)

    @app_commands.command(name="doc", description="Link rápido de guia")
    @app_commands.describe(termo="Ex.: forja, blood moon…")
    async def doc(self, itx: discord.Interaction, termo: str):
        termo_l = termo.lower()
        for k, url in DOCS.items():
            if k in termo_l:
                return await itx.response.send_message(f"🔗 {url}", ephemeral=True)
        await itx.response.send_message("❌ Nenhum documento encontrado.", ephemeral=True)

    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ia_ping(self, itx: discord.Interaction):
        t0  = time.perf_counter()
        gen = self._chat_stream("ping", 'pt')
        await gen.asend(None)
        await itx.response.send_message(f"🏓 {int((time.perf_counter() - t0)*1000)} ms")

    @app_commands.command(name="ia_recarregar", description="Recarrega base (owner)")
    async def recarregar(self, itx: discord.Interaction):
        if itx.user.id != OWNER_ID:
            return await itx.response.send_message("Só o dono. 🚫", ephemeral=True)
        await itx.response.defer(ephemeral=True)
        col.delete_collection()
        await build_vector_db()
        await itx.followup.send("Base recarregada! ✅", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IACog(bot))
