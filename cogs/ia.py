# cogs/ia.py – IA + RAG + Embeds humanizados (build 2025-04-26)

import os, re, time, asyncio, textwrap
from typing import Dict, List

import aiohttp
from bs4 import BeautifulSoup
import discord
from discord.ext import commands
from discord import app_commands

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
from openai import OpenAI, OpenAIError

# ───────────────────────── Config
load_dotenv()
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
OWNER_ID = 470628393272999948
SERVER   = "Anarquia Z"

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
    "https://r.jina.ai/http://x.com/7daystodie",  # versão texto do Twitter
]

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

client   = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=30)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
chroma   = chromadb.PersistentClient(path="chromadb")
col      = chroma.get_or_create_collection("anarquia_z_rag")

# ───────────────────────── Prompt
BASE_PROMPT = textwrap.dedent(f"""
    Olá! Eu sou a <Assistente Z> 🤖 do servidor **{SERVER}**.
    • Especialista em 7 Days to Die 🔨 e Conan Exiles 🗡️
    • Se perguntarem quem é o dono, responda <@{OWNER_ID}>.
    • Quando fizer sentido, convide o jogador a se juntar ao **{SERVER}**.
    Responda em português brasileiro, de forma acolhedora, clara e use emojis quando combinar.
""")

# ───────────────────────── RAG helpers
def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]): t.decompose()
    txt = re.sub(r"\s+", " ", soup.get_text(" "))
    return txt.strip()

def _chunk(text: str, size=500) -> List[str]:
    w = text.split()
    return [" ".join(w[i:i+size]) for i in range(0, len(w), size)]

async def _download(session, url):
    try:
        async with session.get(url, timeout=30) as r:
            return await r.text()
    except Exception as e:
        print(f"[RAG] Falhou {url[:60]}… {e}")
        return ""

async def build_vector_db():
    if col.count():
        return
    print("[RAG] Gerando embeddings…")
    headers = {"User-Agent": "Mozilla/5.0 (RAG-Bot)"}
    async with aiohttp.ClientSession(headers=headers) as sess:
        pages = await asyncio.gather(*[_download(sess, u) for u in LINKS])
        for url, html in zip(LINKS, pages):
            clean = _clean(html)
            for i, chunk in enumerate(_chunk(clean)):
                col.add(ids=[f"{url}#{i}"],
                        documents=[chunk],
                        embeddings=[embedder.encode(chunk).tolist()])
            print(f"[RAG] {url} OK ({len(clean)//1000}k chars)")

def retrieve(query: str, k=5) -> str:
    if not col.count():
        return ""
    vec  = embedder.encode(query).tolist()
    res  = col.query([vec], n_results=k, include=["documents"])
    return "\n---\n".join(res["documents"][0])

# ───────────────────────── Cog
COLOR = 0x8E2DE2
ICON  = "🧟"
COOLDOWN = 60
MAX_EMB = 4000

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last: Dict[int, float] = {}

    async def cog_load(self):
        asyncio.create_task(build_vector_db())

    # OpenAI call
    async def _chat(self, q: str) -> str:
        ctx = retrieve(q)
        msgs = [
            {"role": "system", "content": BASE_PROMPT},
            {"role": "system", "content": f"Contexto:\n{ctx}"},
            {"role": "user",   "content": q},
        ]
        try:
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_ID, messages=msgs,
                max_tokens=512, temperature=0.5
            )
            return resp.choices[0].message.content.strip()
        except OpenAIError as e:
            print("[IA] erro:", e)
            return "Desculpe, a IA falhou agora. 😢"

    # Envio de resposta com "Pensando…"
    async def _send(self, ch, txt, ref=None, itx=None, eph=False):
        # 1) Mensagem temporária
        thinking = None
        if itx:
            await itx.edit_original_response(content="⌛ Pensando…")
        else:
            thinking = await ch.send("⌛ Pensando…", reference=ref)

        # 2) Quebra em embeds
        embeds = []
        for idx, chunk in enumerate([txt[i:i+MAX_EMB] for i in range(0, len(txt), MAX_EMB)]):
            em = discord.Embed(
                title=f"{ICON} Resposta" if idx == 0 else None,
                description=chunk,
                color=COLOR
            )
            if idx == 0:
                em.set_footer(text=f"Assistente • {SERVER}")
            embeds.append(em)

        # 3) Substitui ou edita
        if itx:
            await itx.edit_original_response(content=None, embeds=embeds)
        else:
            await thinking.edit(content=None, embed=embeds[0])
            for extra in embeds[1:]:
                await ch.send(embed=extra)

    # Listener
    @commands.Cog.listener("on_message")
    async def auto(self, msg: discord.Message):
        if msg.author.bot or "?" not in msg.content:
            return
        if time.time() - self.last.get(msg.channel.id, 0) < COOLDOWN:
            return
        resp = await self._chat(msg.content)
        await self._send(msg.channel, resp, ref=msg)
        self.last[msg.channel.id] = time.time()

    # Slash
    @app_commands.command(name="ia", description="Pergunte sobre 7DTD / Conan")
    async def ia(self, itx: discord.Interaction, pergunta: str):
        await itx.response.defer(ephemeral=True, thinking=True)
        resp = await self._chat(pergunta)
        await self._send(itx.channel, resp, itx=itx, eph=True)

    # Ping
    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ia_ping(self, itx: discord.Interaction):
        t0 = time.perf_counter()
        _ = await self._chat("ping")
        await itx.response.send_message(f"🏓 {int((time.perf_counter() - t0)*1000)} ms")

    # Recarregar base
    @app_commands.command(name="ia_recarregar", description="Recarrega base (owner)")
    async def recarregar(self, itx: discord.Interaction):
        if itx.user.id != OWNER_ID:
            return await itx.response.send_message("Só o dono. 🚫", ephemeral=True)
        await itx.response.defer(ephemeral=True, thinking=True)
        col.delete_collection()
        await build_vector_db()
        await itx.followup.send("Base recarregada! ✅", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IACog(bot))
