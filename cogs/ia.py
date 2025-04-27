# cogs/ia.py – IA avançada: RAG+Streaming+Cache(DB)+Cooldown+/doc+Pooling+Retry+Embeds+Metrics+Fallback

import os, re, time, asyncio, textwrap
from datetime import datetime
from typing import Dict, List, Tuple

import aiohttp
import numpy as np
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
from discord import app_commands

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from openai import OpenAI, OpenAIError
import chromadb
from cachetools import TTLCache
from langdetect import detect
from tqdm.asyncio import tqdm_asyncio
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
from loguru import logger
from aioprometheus import Counter, Registry
from aioprometheus.service import Service

# Importa cache persistente em banco e função normalize
from sqlalchemy.exc import SQLAlchemyError
from db import SessionLocal, AICache, normalize

# ─────────────────────────── Configurações
load_dotenv()
API_BASE   = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY    = os.getenv("OPENAI_API_KEY")
MODEL_MAIN = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
MODEL_FALL = os.getenv("OPENAI_MODEL_FALLBACK", "mistralai/Mistral-7B-Instruct-v0.2")
OWNER_ID   = 470628393272999948
SERVER     = "Anarquia Z"

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

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

# Cliente OpenAI e embeddings
client   = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=30)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Backend vetorial (Chroma ou pgvector)
from chromadb.config import Settings
if os.getenv("PGVECTOR_URL"):
    chroma_client = chromadb.PersistentClient(settings=Settings(
        chroma_db_impl="postgres", connection_uri=os.getenv("PGVECTOR_URL"), anonymized_telemetry=False
    ))
else:
    chroma_client = chromadb.PersistentClient(path="chromadb")
col = chroma_client.get_or_create_collection("anarquia_z_rag")

# Pooling em RAM
_mem_docs: List[str] = []
_mem_vecs: List[np.ndarray] = []

# Prompts base
PROMPT_PT = textwrap.dedent(f"""
Olá! Eu sou a <Assistente Z> 🤖 do servidor **{SERVER}**.
• Especialista em 7 Days to Die 🔨 e Conan Exiles 🗡️
• Se perguntarem quem é o dono, responda <@{OWNER_ID}>.
• Quando fizer sentido, convide para **{SERVER}**.
Responda em PT-BR, acolhedor, claro, com emojis.
"""
)
PROMPT_EN = textwrap.dedent(f"""
Hi! I'm <Assistant Z> 🤖 from **{SERVER}**.
• I cover 7 Days to Die 🔨 and Conan Exiles 🗡️.
• The server owner is <@{OWNER_ID}>.
• Feel free to join **{SERVER}**!
Answer in friendly, concise English with emojis.
"""
)

# Métricas Prometheus
registry     = Registry()
CACHE_HITS   = Counter("ia_cache_hits", "Cache DB hits")
CACHE_MISSES = Counter("ia_cache_misses", "Cache DB misses")
API_CALLS    = Counter("ia_api_calls", "API calls count")
TOKENS_USED  = Counter("ia_tokens_used", "Total tokens used")
registry.register(CACHE_HITS)
registry.register(CACHE_MISSES)
registry.register(API_CALLS)
registry.register(TOKENS_USED)
service = Service()

# Controle e cache
CACHE_TTL = TTLCache(maxsize=2048, ttl=43200)
COOLDOWN  = 60
MAX_LEN   = 4000
COLOR     = 0x8E2DE2
ICON      = "🧟"

# Cache DB helpers

def db_get_cached(raw_q: str) -> str | None:
    key = normalize(raw_q)
    with SessionLocal() as db:
        row = db.query(AICache).filter_by(question=key).first()
        if row:
            CACHE_HITS.inc({})
            logger.info(f"Cache hit: {key}")
            return row.answer
    CACHE_MISSES.inc({})
    return None


def db_set_cached(raw_q: str, ans: str):
    key = normalize(raw_q)
    with SessionLocal() as db:
        try:
            row = db.query(AICache).filter_by(question=key).first()
            if row:
                row.answer     = ans
                row.updated_at = datetime.utcnow()
            else:
                db.add(AICache(question=key, answer=ans))
            db.commit()
            logger.info(f"Cached answered: {key}")
        except SQLAlchemyError as e:
            db.rollback(); logger.error(f"AI-Cache error: {e}")

# RAG helpers e pooling

def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script","style","noscript"]): t.decompose()
    return re.sub(r"\s+"," ", soup.get_text(" ")).strip()

def _chunk(text: str, size: int=500) -> List[str]:
    w = text.split()
    return [" ".join(w[i:i+size]) for i in range(0,len(w),size)]

async def _download(session, url: str) -> str:
    try:
        async with session.get(url, timeout=30) as r:
            return await r.text()
    except Exception as e:
        logger.warning(f"RAG fetch fail {url}: {e}")
        return ""

async def build_vector_db():
    if col.count(): return
    logger.info("Building RAG index…")
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as sess:
        pages = await tqdm_asyncio.gather(*[_download(sess,u) for u in LINKS])
    docs, embs = [], []
    for url, html in zip(LINKS, pages):
        txt = _clean(html)
        for i,ch in enumerate(_chunk(txt)):
            emb = embedder.encode(ch).tolist()
            col.add(ids=[f"{url}#{i}"], documents=[ch], embeddings=[emb])
            docs.append(ch); embs.append(np.array(emb))
        logger.info(f"Indexed {url} ({len(txt)//1000}k chars)")
    global _mem_docs, _mem_vecs
    _mem_docs, _mem_vecs = docs, embs

def retrieve_ctx(question: str, k: int=5) -> str:
    if not _mem_vecs: return ""
    qv = embedder.encode(question)
    sims = [float(np.dot(qv,v)) for v in _mem_vecs]
    idxs = sorted(range(len(sims)), key=lambda i:-sims[i])[:k]
    return "\n---\n".join(_mem_docs[i] for i in idxs)

# LLM call com retry e fallback
async def call_llm(msgs):
    for model in [MODEL_MAIN, MODEL_FALL]:
        try:
            async for attempt in AsyncRetrying(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(1,10)):
                with attempt:
                    resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        model=model, messages=msgs,
                        temperature=0.5, max_tokens=512, stream=True
                    )
                    API_CALLS.inc({"model":model})
                    TOKENS_USED.inc({"model":model,"tokens":resp.usage.total_tokens})
                    return resp
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
    raise RuntimeError("All models failed")

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot; self.last: Dict[Tuple[int,int],float] = {}

    async def cog_load(self):
        await service.start(addr="0.0.0.0", port=8000)
        asyncio.create_task(build_vector_db())
        self.refresh_embeddings.start()

    @tasks.loop(hours=24)
    async def refresh_embeddings(self):
        col.delete_collection(); await build_vector_db()

    async def _chat_stream(self, prompt: str, lang: str):
        cached_db = db_get_cached(prompt)
        if cached_db: yield cached_db; return
        key = normalize(prompt)
        if key in CACHE_TTL: yield CACHE_TTL[key]; return
        sys_p = PROMPT_EN if lang=='en' else PROMPT_PT
        ctx = retrieve_ctx(prompt)
        msgs=[{"role":"system","content":sys_p}, {"role":"system","content":f"Context: {ctx}"}, {"role":"user","content":prompt}]
        full=""
        resp = await call_llm(msgs)
        for chunk in resp:
            full+=chunk.choices[0].delta.content or ""; yield full
        db_set_cached(prompt, full); CACHE_TTL[key]=full

    async def _stream_to_channel(self, ch, prompt, ref=None, itx=None, eph=False):
        lang = 'en' if detect(prompt)=='en' else 'pt'
        if itx: await itx.edit_original_response(content="⌛ Pensando…")
        else: thinking=await ch.send("⌛ Pensando…", reference=ref)
        temp=itx if itx else thinking; final=""
        async for part in self._chat_stream(prompt, lang): final=part; snippet=final[-MAX_LEN:];
        if itx: await itx.edit_original_response(content=snippet)
        else: await temp.edit(content=snippet)
        title=final.split('.')[0][:50] or ICON
        emb=discord.Embed(title=title, description=final, color=COLOR)
        emb.set_footer(text=f"Assistente • {SERVER}")
        if itx: await itx.edit_original_response(content=None, embed=emb)
        else: await temp.edit(content=None, embed=emb)

    @commands.Cog.listener("on_message")
    async def auto(self, msg: discord.Message):
        if msg.author.bot or '?' not in msg.content: return
        key=(msg.channel.id,msg.author.id)
        if time.time()-self.last.get(key,0)<COOLDOWN: return
        await self._stream_to_channel(msg.channel,msg.content,ref=msg)
        self.last[key]=time.time()

    @app_commands.command(name="ia", description="Pergunte algo sobre 7DTD / Conan")
    @app_commands.describe(pergunta="Sua dúvida")
    async def ia(self,itx:discord.Interaction, pergunta:str):
        await itx.response.defer(ephemeral=True); await self._stream_to_channel(itx.channel, pergunta, itx=itx, eph=True)

    @app_commands.command(name="doc", description="Link rápido de guia")
    @app_commands.describe(termo="Ex.: forja, blood moon…")
    async def doc(self,itx:discord.Interaction, termo:str):
        for k,url in DOCS.items():
            if k in termo.lower(): return await itx.response.send_message(f"🔗 {url}", ephemeral=True)
        await itx.response.send_message("❌ Nenhum documento encontrado.", ephemeral=True)

    @app_commands.command(name="ia_clearcache", description="Limpa todo cache da IA (owner)")
    async def clearcache(self,itx:discord.Interaction):
        if itx.user.id!=OWNER_ID: return await itx.response.send_message("Só o dono. 🚫",ephemeral=True)
        await itx.response.defer(ephemeral=True)
        with SessionLocal() as db: db.query(AICache).delete(); db.commit()
        CACHE_TTL.clear()
        await itx.followup.send("Cache limpo! ✅",ephemeral=True)

    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ia_ping(self,itx:discord.Interaction):
        t0=time.perf_counter(); gen=self._chat_stream("ping",'pt'); await gen.asend(None)
        await itx.response.send_message(f"🏓 {int((time.perf_counter()-t0)*1000)} ms")

    @app_commands.command(name="ia_recarregar", description="Recria RAG index (owner)")
    async def recarregar(self,itx:discord.Interaction):
        if itx.user.id!=OWNER_ID: return await itx.response.send_message("Só o dono. 🚫",ephemeral=True)
        await itx.response.defer(ephemeral=True)
        col.delete_collection(); await build_vector_db()
        await itx.followup.send("RAG index recriado! ✅",ephemeral=True)

async def setup(bot): await bot.add_cog(IACog(bot))
