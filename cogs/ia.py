# cogs/ia.py – IA avançada: RAG+Streaming+Cache(DB)+Cooldown+/doc+Pooling+Retry+Embeds+Metrics+Fallback

import os
import re
import time
import asyncio
import textwrap
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import aiohttp
import numpy as np
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui

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

from sqlalchemy.exc import SQLAlchemyError
from db import SessionLocal, AICache, normalize

# ─────────────────────────── Configurações ─────────────────────────────────────
load_dotenv()

# OpenAI
API_BASE   = os.getenv("OPENAI_API_BASE",   "https://api.deepinfra.com/v1/openai")
API_KEY    = os.getenv("OPENAI_API_KEY")
MODEL_MAIN = os.getenv("OPENAI_MODEL",      "meta-llama/Meta-Llama-3-8B-Instruct")
MODEL_FALL = os.getenv("OPENAI_MODEL_FALLBACK", "mistralai/Mistral-7B-Instruct-v0.2")

# Bot & Server
OWNER_ID = int(os.getenv("OWNER_ID",      "470628393272999948"))
SERVER   = os.getenv("SERVER_NAME",       "Anarquia Z")

# CAMI Host panel API
PANEL_URL   = os.getenv("CAMI_API_BASE")    # ex: https://painel.camy.host/api/client
PANEL_TOKEN = os.getenv("CAMI_API_TOKEN")   # seu token
SERVER_ID   = os.getenv("CAMI_SERVER_ID")   # ID do servidor

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

# utilitário CAMI API
async def cami_request(path: str, method: str = "GET", json: Optional[dict] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {PANEL_TOKEN}",
        "Content-Type":    "application/json"
    }
    url = f"{PANEL_URL}/servers/{SERVER_ID}{path}"
    async with aiohttp.ClientSession() as sess:
        resp = await sess.request(method, url, headers=headers, json=json, timeout=15)
        resp.raise_for_status()
        return await resp.json()

# RAG LINKS & DOCS
LINKS = [
    "https://anarquia-z.netlify.app/",
    "https://7daystodie.com/",
    "https://7daystodie.com/changelog/",
    "https://7daystodie.com/blogs/news/",
    "https://7daystodie.com/support/",
    "https://steamcommunity.com/app/251570/discussions/",
    "https://7daystodie.fandom.com/wiki/Beginners_Guide",
    "https://7daystodie.fandom.com/wiki/1.0_Series",
    "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "https://7daystodie.fandom.com/wiki/List_of_Zombies",
    "https://7daystodie.fandom.com/wiki/Traps_and_Defenses",
    "https://7daystodie.fandom.com/wiki/Perks",
    "https://7daystodie.fandom.com/wiki/Weapon_Attachments",
    "https://7daystodie.fandom.com/wiki/Alchemy_Page",
    "https://7daystodie.fandom.com/wiki/Technology_Tree",
    "https://navezgane.map/",
    "https://developer.valvesoftware.com/wiki/7_Days_to_Die_Dedicated_Server_Setup",
    "https://7daystodie-servers.com/server/151960/",
    "https://ultahost.com/blog/pt/top-5-piores-perks-em-7-days-to-die/",
    "https://www.reddit.com/r/7daystodie/",
    "https://next.nexusmods.com/profile/NoVaErAPvE?gameId=1059",
    "https://www.youtube.com/c/TheOfficial7DaysToDie"
]
DOCS = {
    "forja":      "https://7daystodie.fandom.com/wiki/Forging_System",
    "blood moon": "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "zumbis":     "https://7daystodie.fandom.com/wiki/List_of_Zombies",
}

# Cliente OpenAI, embeddings e ChromaDB
client   = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=30)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
from chromadb.config import Settings
if os.getenv("PGVECTOR_URL"):
    chroma_client = chromadb.PersistentClient(settings=Settings(
        chroma_db_impl="postgres",
        connection_uri=os.getenv("PGVECTOR_URL"),
        anonymized_telemetry=False
    ))
else:
    chroma_client = chromadb.PersistentClient(path="chromadb")
col = chroma_client.get_or_create_collection("anarquia_z_rag")

# Pooling em RAM
_mem_docs: List[str]        = []
_mem_vecs: List[np.ndarray] = []

PROMPT_PT = textwrap.dedent(f"""
Você está falando com a **Assistente Z** 🤖, a IA oficial do servidor **{SERVER}** (IP: 191.37.92.145:26920).
• Especialista em **7 Days to Die** 🔨 e suporte ao **{SERVER}**.
• Responda **apenas** sobre 7 Days to Die, mods, gameplay, status e suporte.
• Se perguntarem quem é o dono, mencione <@{OWNER_ID}>.
""")
PROMPT_EN = textwrap.dedent(f"""
You are **Assistant Z** 🤖, the official AI of the **{SERVER}** server.
• Your expertise is support and info about **7 Days to Die** 🔨 and **{SERVER}**.
• Respond **only** about 7 Days to Die, mods, gameplay, server status and support.
• If asked who the owner is, mention <@{OWNER_ID}>.
""")

# Métricas Prometheus
registry     = Registry()
CACHE_HITS   = Counter("ia_cache_hits",   "Cache DB hits")
CACHE_MISSES = Counter("ia_cache_misses", "Cache DB misses")
API_CALLS    = Counter("ia_api_calls",    "API calls count")
TOKENS_USED  = Counter("ia_tokens_used",  "Total tokens used")
for m in (CACHE_HITS, CACHE_MISSES, API_CALLS, TOKENS_USED):
    registry.register(m)
service = Service()

# Controle e cache
CACHE_TTL = TTLCache(maxsize=2048, ttl=43200)
COOLDOWN  = 60
MAX_LEN   = 4000
COLOR     = 0x8E2DE2
ICON      = "🧟"

# Regex e View de botões para links
URL_REGEX = re.compile(r'(https?://[^\s]+)')
def make_link_view(text: str) -> ui.View:
    view = ui.View()
    seen = set()
    for url in URL_REGEX.findall(text):
        if url in seen:
            continue
        seen.add(url)
        label = url.replace("https://","").replace("http://","")
        if len(label) > 40:
            label = label[:37] + "..."
        view.add_item(ui.Button(label=label, url=url))
    return view

# Cache DB helpers
def db_get_cached(raw_q: str) -> Optional[str]:
    key = normalize(raw_q)
    with SessionLocal() as db:
        row = db.query(AICache).filter_by(question=key).first()
        if row:
            CACHE_HITS.inc({})
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
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"AI-Cache error: {e}")

# RAG helpers & pooling
def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script","style","noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()

def _chunk(text: str, size: int = 500) -> List[str]:
    w = text.split()
    return [" ".join(w[i:i+size]) for i in range(0, len(w), size)]

async def _download(session, url: str) -> str:
    try:
        async with session.get(url, timeout=30) as r:
            return await r.text()
    except:
        return ""

async def build_vector_db():
    if col.count():
        return
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as sess:
        pages = await tqdm_asyncio.gather(*[_download(sess, u) for u in LINKS])
    docs, embs = [], []
    for url, html in zip(LINKS, pages):
        txt = _clean(html)
        for i, ch in enumerate(_chunk(txt)):
            emb = embedder.encode(ch).tolist()
            col.add(ids=[f"{url}#{i}"], documents=[ch], embeddings=[emb])
            docs.append(ch)
            embs.append(np.array(emb))
    global _mem_docs, _mem_vecs
    _mem_docs, _mem_vecs = docs, embs

def retrieve_ctx(question: str, k: int = 5) -> str:
    if not _mem_vecs:
        return ""
    qv   = embedder.encode(question)
    sims = [float(np.dot(qv, v)) for v in _mem_vecs]
    idxs = sorted(range(len(sims)), key=lambda i: -sims[i])[:k]
    return "\n---\n".join(_mem_docs[i] for i in idxs)

# LLM call com retry e fallback
async def call_llm(msgs):
    for model in (MODEL_MAIN, MODEL_FALL):
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(1,10)
            ):
                with attempt:
                    resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        model=model,
                        messages=msgs,
                        temperature=0.3,
                        max_tokens=512,
                        stream=True
                    )
                    API_CALLS.inc({"model": model})
                    return resp
        except:
            continue
    raise RuntimeError("All models failed")

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot  = bot
        self.last = {}  # (channel_id, user_id) → timestamp

    async def cog_load(self):
        await service.start(addr="0.0.0.0", port=8000)
        asyncio.create_task(build_vector_db())
        self.refresh_embeddings.start()

    @tasks.loop(hours=24)
    async def refresh_embeddings(self):
        col.delete_collection()
        await build_vector_db()

    async def _chat_stream(self, prompt: str, lang: str):
        cached = db_get_cached(prompt)
        if cached:
            yield cached; return
        key = normalize(prompt)
        if key in CACHE_TTL:
            yield CACHE_TTL[key]; return
        sys_p = PROMPT_EN if lang=='en' else PROMPT_PT
        ctx   = retrieve_ctx(prompt)
        msgs  = [
            {"role":"system","content":sys_p},
            {"role":"system","content":f"Context: {ctx}"},
            {"role":"user",  "content":prompt}
        ]
        full = ""
        try:
            stream = await call_llm(msgs)
        except:
            yield "❌ IA indisponível."; return
        async for chunk in stream:
            full += chunk.choices[0].delta.content or ""
            yield full
        db_set_cached(prompt, full)
        CACHE_TTL[key] = full

    async def _stream_to_channel(self, ch, prompt, ref=None, itx=None, eph=False):
        if itx:
            await itx.edit_original_response(content="⌛ Pensando…")
        else:
            thinking = await ch.send("⌛ Pensando…", reference=ref)
        temp = itx or thinking

        content = prompt.lower()
        me      = self.bot.user.id
        # dispara se '?' em content ou comando 'ia ' ou menção
        if not ('?' in content or content.startswith('ia ') or me in [u.id for u in (await ch.guild.fetch_member(me)).roles]):
            # (isso é ignorado aqui, pois on_message trata; mantém coerência)
            pass

        lang = 'en' if detect(prompt)=='en' else 'pt'
        sys_p = PROMPT_EN if lang=='en' else PROMPT_PT
        final = ""

        try:
            async with asyncio.timeout(30):
                async for part in self._chat_stream(prompt, lang):
                    final = part
                    snippet = final[-MAX_LEN:]
                    try:
                        if itx:
                            await itx.edit_original_response(content=snippet)
                        else:
                            await temp.edit(content=snippet)
                    except discord.HTTPException:
                        pass
        except asyncio.TimeoutError:
            # fallback sem stream
            fallback = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_MAIN,
                messages=[{"role":"system","content":sys_p},{"role":"user","content":prompt}],
                temperature=0.3,
                max_tokens=512
            )
            final = fallback.choices[0].message.content

        title = final.split('.')[0][:50] or ICON
        emb   = discord.Embed(title=title, description=final, color=COLOR)
        emb.set_footer(text=f"Assistente • {SERVER}")
        view  = make_link_view(final)

        if itx:
            await itx.edit_original_response(content=None, embed=emb, view=view)
        else:
            await temp.edit(content=None, embed=emb, view=view)

    @commands.Cog.listener("on_message")
    async def auto(self, msg: discord.Message):
        if msg.author.bot:
            return
        content = msg.content.lower()
        me      = self.bot.user.id
        if ('?' not in content 
            and not content.startswith('ia ') 
            and me not in [u.id for u in msg.mentions]):
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
        for k, url in DOCS.items():
            if k in termo.lower():
                view = ui.View()
                view.add_item(ui.Button(label=k.title(), url=url))
                return await itx.response.send_message("🔗 Aqui está o guia:", view=view, ephemeral=True)
        await itx.response.send_message("❌ Nenhum documento encontrado.", ephemeral=True)

    @app_commands.command(name="status", description="📡 Status do servidor Anarquia Z")
    async def status(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        try:
            info = await cami_request("")
        except Exception as e:
            return await itx.followup.send(f"❌ Erro API CAMI: {e}", ephemeral=True)
        attrs  = info.get("attributes", {})
        status = attrs.get("status", "—")
        players= attrs.get("players", 0)
        maxp   = attrs.get("max_players", 0)
        try:
            res     = await cami_request("/resources")
            r_attrs = res.get("attributes", {})
            cpu     = r_attrs.get("cpu_absolute", 0.0)
            ram_mb  = r_attrs.get("memory_bytes", 0) // (1024**2)
        except:
            cpu = ram_mb = None
        emb = discord.Embed(title="📡 Status Anarquia Z", color=COLOR)
        emb.add_field(name="Status",    value=status, inline=True)
        emb.add_field(name="Jogadores", value=f"{players}/{maxp}", inline=True)
        if cpu is not None:
            emb.add_field(name="CPU (%)",  value=f"{cpu:.1f}", inline=True)
            emb.add_field(name="RAM (MB)", value=str(ram_mb), inline=True)
        emb.set_footer(text=f"Atualizado em {datetime.utcnow():%d/%m/%Y %H:%M UTC}")
        await itx.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="restart", description="🔄 Reinicia o servidor Anarquia Z")
    async def restart(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        try:
            await cami_request("/power", method="POST", json={"signal":"restart"})
        except Exception as e:
            return await itx.followup.send(f"❌ Erro ao reiniciar: {e}", ephemeral=True)
        await itx.followup.send("🔄 Servidor reiniciado com sucesso!", ephemeral=True)

    @app_commands.command(name="ia_clearcache", description="Limpa cache IA (owner)")
    async def clearcache(self, itx: discord.Interaction):
        if itx.user.id != OWNER_ID:
            return await itx.response.send_message("Só o dono. 🚫", ephemeral=True)
        await itx.response.defer(ephemeral=True)
        with SessionLocal() as db:
            db.query(AICache).delete()
            db.commit()
        CACHE_TTL.clear()
        await itx.followup.send("Cache limpo! ✅", ephemeral=True)

    @app_commands.command(name="ia_ping", description="🏓 Latência da IA")
    async def ia_ping(self, itx: discord.Interaction):
        t0 = time.perf_counter()
        gen = self._chat_stream("ping", 'pt')
        await gen.asend(None)
        await itx.response.send_message(f"🏓 {int((time.perf_counter()-t0)*1000)} ms")

    @app_commands.command(name="ia_recarregar", description="♻️ Recria RAG index (owner)")
    async def recarregar(self, itx: discord.Interaction):
        if itx.user.id != OWNER_ID:
            return await itx.response.send_message("Só o dono. 🚫", ephemeral=True)
        await itx.response.defer(ephemeral=True)
        col.delete_collection()
        await build_vector_db()
        await itx.followup.send("♻️ RAG index recriado! ✅", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IACog(bot))
