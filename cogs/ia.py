# cogs/ia.py – IA + RAG (scrape links) + embed bonito
import os, re, time, asyncio, textwrap, requests
from bs4 import BeautifulSoup
from typing import Dict, List

import discord
from discord.ext import commands, tasks
from discord import app_commands

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
from openai import OpenAI, OpenAIError

# ───────────────────────────────  Config
load_dotenv()
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepinfra.com/v1/openai")
API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_ID = os.getenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
OWNER_ID = 470628393272999948
SERVER   = "Anarquia Z"

LINKS = [
    "https://anarquia-z.netlify.app/",
    "https://x.com/7daystodie",
    "https://7daystodie.fandom.com/wiki/Beginners_Guide",
    "https://7daystodie.fandom.com/wiki/Blood_Moon_Horde",
    "https://7daystodie.com",
    "https://next.nexusmods.com/profile/NoVaErAPvE?gameId=1059",
]

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido!")

client   = OpenAI(base_url=API_BASE, api_key=API_KEY)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
chroma   = chromadb.PersistentClient(path="chromadb")
col      = chroma.get_or_create_collection("anarquia_z_rag")

# ───────────────────────────────  Prompt base
BASE_PROMPT = textwrap.dedent(f"""
    Você é a assistente oficial do servidor **{SERVER}**.
    Jogos cobertos: 7 Days to Die e Conan Exiles.
    Sempre que fizer sentido convide o jogador a entrar no **{SERVER}**.
    Se perguntarem quem é o dono, responda <@{OWNER_ID}>.
    Responda em português brasileiro, de forma curta e objetiva.
""")

# ───────────────────────────────  Funções RAG
def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _chunk(text: str, size: int = 500) -> List[str]:
    words = text.split()
    return [" ".join(words[i:i+size]) for i in range(0, len(words), size)]

def build_vector_db():
    if col.count() > 0:
        return  # já existe
    print("[RAG] Construindo base vetorial…")
    for url in LINKS:
        try:
            html = requests.get(url, timeout=20).text
            clean = _clean_html(html)
            for i, chunk in enumerate(_chunk(clean)):
                vec = embedder.encode(chunk).tolist()
                col.add(ids=[f"{url}#{i}"], documents=[chunk], embeddings=[vec])
            print(f"[RAG] {url} OK")
        except Exception as e:
            print(f"[RAG] Falhou {url}: {e}")

def retrieve_context(query: str, k: int = 3) -> str:
    if col.count() == 0:
        return ""
    qvec = embedder.encode(query).tolist()
    res  = col.query(query_embeddings=[qvec], n_results=k, include=["documents"])
    return "\n---\n".join(res["documents"][0])

# ───────────────────────────────  Cog
COLOR = 0x8E2DE2
ICON  = "🧟"
COOLDOWN = 60

class IACog(commands.Cog):
    def __init__(self, bot):
        self.bot     = bot
        self.last: Dict[int,float] = {}
        # gera vetores na 1ª carga (em thread p/ não travar)
        bot.loop.create_task(asyncio.to_thread(build_vector_db))

    # ===== Chat =====
    async def _chat(self, q: str) -> str:
        context = retrieve_context(q)
        messages = [
            {"role":"system","content":BASE_PROMPT},
            {"role":"system","content":f"Contexto relevante:\n{context}"},
            {"role":"user",  "content":q},
        ]
        try:
            r = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_ID,
                messages=messages,
                max_tokens=512, temperature=0.3,
            )
            return r.choices[0].message.content.strip()
        except OpenAIError as e:
            print("[IA] erro:", e)
            return "Desculpe, a IA está indisponível agora."

    async def _send_embed(self, channel, ans, ref=None, itx=None, eph=False):
        emb = discord.Embed(title=f"{ICON} Resposta da IA", description=ans, color=COLOR)
        emb.set_footer(text=f"Assistente • {SERVER}")
        if itx:
            await itx.followup.send(embed=emb, ephemeral=eph)
        else:
            await channel.send(embed=emb, reference=ref)

    # ===== Listener =====
    @commands.Cog.listener("on_message")
    async def auto(self, m: discord.Message):
        if m.author.bot: return
        if "?" not in m.content and "ajuda" not in m.content.lower(): return
        if time.time()-self.last.get(m.channel.id,0) < COOLDOWN: return
        ans = await self._chat(m.content)
        await self._send_embed(m.channel, ans, ref=m)
        self.last[m.channel.id] = time.time()

    # ===== Slash =====
    @app_commands.command(name="ia", description="Pergunte algo sobre 7DTD ou Conan")
    async def ia(self, itx: discord.Interaction, pergunta: str):
        await itx.response.defer(thinking=True, ephemeral=True)
        ans = await self._chat(pergunta)
        await self._send_embed(itx.channel, ans, itx=itx, eph=True)

    @app_commands.command(name="ia_ping", description="Latência da IA")
    async def ping(self, itx: discord.Interaction):
        t0=time.perf_counter(); _=await self._chat("pong?")
        await itx.response.send_message(f"🏓 {int((time.perf_counter()-t0)*1000)} ms")

    # ===== Recarregar vetores =====
    @app_commands.command(name="ia_recarregar", description="Regera a base de conhecimento (admin)")
    async def recarregar(self, itx: discord.Interaction):
        if itx.user.id != OWNER_ID:
            await itx.response.send_message("Só o dono pode recarregar.", ephemeral=True)
            return
        await itx.response.defer(thinking=True, ephemeral=True)
        col.delete_collection()
        build_vector_db()
        await itx.followup.send("Base recarregada!", ephemeral=True)

async def setup(bot): await bot.add_cog(IACog(bot))
