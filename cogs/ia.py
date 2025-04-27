# cogs/ia.py – IA + RAG + embed (versão 2025-04)

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

# ─────────────────────── Config
load_dotenv()
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
OWNER_ID = 470628393272999948
SERVER   = "Anarquia Z"

LINKS = [
    "https://anarquia-z.netlify.app",
    "https://x.com/7daystodie",
    "https://7daystodie.fandom.com/wiki/Beginners_Guide",
    "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "https://7daystodie.com",
    "https://next.nexusmods.com/profile/NoVaErAPvE?gameId=1059",
]

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

client   = OpenAI(base_url=API_BASE, api_key=API_KEY, timeout=30)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
chroma   = chromadb.PersistentClient(path="chromadb")
col      = chroma.get_or_create_collection("anarquia_z_rag")

# ─────────────────────── Prompt
BASE_PROMPT = textwrap.dedent(f"""
    Você é a assistente oficial do servidor **{SERVER}**.
    Jogos cobertos: 7 Days to Die e Conan Exiles.
    Se perguntarem quem é o dono, responda <@{OWNER_ID}>.
    Quando fizer sentido, convide o jogador a juntar-se ao **{SERVER}**.
    Use português brasileiro, seja direto e amigável.
""")

# ─────────────────────── Utilidades RAG
def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]): t.decompose()
    txt = re.sub(r"\s+", " ", soup.get_text(" "))
    return txt.strip()

def _chunk(text: str, size=500) -> List[str]:
    w = text.split(); return [" ".join(w[i:i+size]) for i in range(0, len(w), size)]

async def download(session, url):
    try:
        async with session.get(url, timeout=20) as r:
            return await r.text()
    except Exception as e:
        print(f"[RAG] Falhou {url[:60]}… {e}")
        return ""

async def build_vector_db():
    if col.count() > 0:
        return
    print("[RAG] Gerando embeddings…")
    hdrs = {"User-Agent": "Mozilla/5.0 (RAG-Bot)"}
    async with aiohttp.ClientSession(headers=hdrs) as sess:
        tasks = [download(sess, u) for u in LINKS]
        for url, html in zip(LINKS, await asyncio.gather(*tasks)):
            clean = _clean(html)
            for i, chunk in enumerate(_chunk(clean)):
                vec = embedder.encode(chunk).tolist()
                col.add(ids=[f"{url}#{i}"], documents=[chunk], embeddings=[vec])
            print(f"[RAG] {url} OK ({len(clean)//1000}k chars)")

def retrieve(query: str, k=3) -> str:
    if col.count()==0: return ""
    qvec = embedder.encode(query).tolist()
    res  = col.query([qvec], n_results=k, include=["documents"])
    return "\n---\n".join(res["documents"][0])

# ─────────────────────── Cog
COLOR = 0x8E2DE2; ICON="🧟"; COOLDOWN=60; MAX_EMB=4000

class IACog(commands.Cog):
    def __init__(self, bot): self.bot, self.last = bot, {}

    async def cog_load(self):               # <- SAFE init
        asyncio.create_task(build_vector_db())

    async def _chat(self, q:str) -> str:
        ctx = retrieve(q)
        msgs=[{"role":"system","content":BASE_PROMPT},
              {"role":"system","content":f"Contexto:\n{ctx}"},
              {"role":"user","content":q}]
        try:
            r = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_ID, messages=msgs,
                max_tokens=512, temperature=0.3)
            return r.choices[0].message.content.strip()
        except OpenAIError as e:
            print("[IA] erro:", e); return "Desculpe, a IA falhou agora."

    async def _send(self, ch, txt, ref=None, itx=None, eph=False):
        chunks = [txt[i:i+MAX_EMB] for i in range(0,len(txt),MAX_EMB)]
        for idx,c in enumerate(chunks):
            emb=discord.Embed(title=f"{ICON} Resposta da IA" if idx==0 else None,
                              description=c, color=COLOR)
            if idx==0: emb.set_footer(text=f"Assistente • {SERVER}")
            if itx: await itx.followup.send(embed=emb, ephemeral=eph)
            else:   await ch.send(embed=emb, reference=ref)

    # Listener
    @commands.Cog.listener("on_message")
    async def auto(self, m:discord.Message):
        if m.author.bot or "?" not in m.content: return
        if time.time()-self.last.get(m.channel.id,0)<COOLDOWN: return
        ans=await self._chat(m.content); await self._send(m.channel, ans, ref=m)
        self.last[m.channel.id]=time.time()

    # Slash
    @app_commands.command(name="ia", description="Pergunte sobre 7DTD/Conan")
    async def ia(self,itx:discord.Interaction, pergunta:str):
        await itx.response.defer(ephemeral=True, thinking=True)
        await self._send(itx.channel, await self._chat(pergunta), itx=itx, eph=True)

    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ia_ping(self,itx:discord.Interaction):
        t0=time.perf_counter(); _=await self._chat("ping")
        await itx.response.send_message(f"🏓 {int((time.perf_counter()-t0)*1e3)} ms")

    @app_commands.command(name="ia_recarregar", description="Recarrega base (owner)")
    async def recarregar(self,itx:discord.Interaction):
        if itx.user.id!=OWNER_ID:
            return await itx.response.send_message("Só o dono.", ephemeral=True)
        await itx.response.defer(ephemeral=True, thinking=True)
        col.delete_collection(); await build_vector_db()
        await itx.followup.send("Base recarregada!", ephemeral=True)

async def setup(bot): await bot.add_cog(IACog(bot))
