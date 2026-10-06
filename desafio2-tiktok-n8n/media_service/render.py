"""Renderiza um roteiro em vídeo vertical 1080x1920 (formato TikTok).

Por cena:
  - fundo: foto do Pexels ou Pixabay (busca pelas palavras-chave da cena) ou degradê, sem chave/rede;
  - emoji grande escolhido pelo roteiro (fonte Segoe UI Emoji, colorida, offline);
  - texto principal num painel translúcido;
  - narração neural pt-BR (edge-tts) com o tempo de cada palavra.
No vídeo final:
  - transições em crossfade entre as cenas (xfade + acrossfade);
  - legendas dinâmicas palavra a palavra (ASS), sincronizadas com a narração;
  - trilha de fundo composta pelo próprio programa (numpy), sem direitos autorais, que abaixa
    automaticamente quando há fala (sidechain).
Cada recurso degrada com elegância: sem internet o vídeo sai mudo e com degradê, mas sai.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import shutil
import subprocess
import textwrap
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
FPS = 30
TRANSICAO = 0.35          # segundos de crossfade entre cenas
VOZ = "pt-BR-AntonioNeural"
FONTES = Path("C:/Windows/Fonts")
PALETA = [((14, 30, 74), (37, 87, 167)), ((20, 20, 40), (90, 40, 140)), ((8, 60, 70), (20, 130, 120))]
DESTAQUE = (247, 168, 35)
MARCA = "@automacao.na.pratica"
BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "output" / "_cache_fotos"


# ----------------------------------------------------------------- utilidades
def _chave(nome: str) -> str:
    """Lê a chave do ambiente ou do .env do Desafio 2."""
    chave = os.getenv(nome, "").strip()
    env = BASE / ".env"
    if not chave and env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith(f"{nome}="):
                chave = linha.split("=", 1)[1].strip()
    return chave


def _fonte(tamanho: int, negrito: bool = True) -> ImageFont.FreeTypeFont:
    for nome in (("segoeuib.ttf", "arialbd.ttf") if negrito else ("segoeui.ttf", "arial.ttf")):
        if (FONTES / nome).exists():
            return ImageFont.truetype(str(FONTES / nome), tamanho)
    return ImageFont.load_default(tamanho)


def _ffmpeg(*args: str, cwd: Path | None = None) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        raise RuntimeError(f"ffmpeg falhou: {r.stderr[-800:]}")


def _duracao(arq: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(arq)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


# ------------------------------------------------------------------- fundos
def _degrade(i: int) -> Image.Image:
    topo, base = PALETA[i % len(PALETA)]
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / H
        grad.putpixel((0, y), tuple(int(topo[c] * (1 - t) + base[c] * t) for c in range(3)))
    img = grad.resize((W, H))
    luz = Image.new("L", (W, H), 0)
    ImageDraw.Draw(luz).ellipse((W - 700, -300, W + 300, 700), fill=90)
    luz = luz.filter(ImageFilter.GaussianBlur(160))
    return Image.composite(Image.new("RGB", (W, H), DESTAQUE), img, luz.point(lambda v: v // 3))


def _url_pexels(busca: str, semente: int, chave: str) -> str | None:
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": busca, "orientation": "portrait", "per_page": 8, "size": "large"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": chave}), timeout=20) as r:
        fotos = json.load(r).get("photos", [])
    if not fotos:
        return None
    return fotos[semente % len(fotos)]["src"]["original"] + f"?auto=compress&cs=tinysrgb&fit=crop&w={W}&h={H}"


def _url_pixabay(busca: str, semente: int, chave: str) -> str | None:
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(
        {"key": chave, "q": busca[:100], "image_type": "photo", "orientation": "vertical", "per_page": 10,
         "safesearch": "true", "min_height": 1200})
    # o Pixabay (atrás do Cloudflare) recusa o User-Agent padrão do Python com "error code: 1010"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        fotos = json.load(r).get("hits", [])
    if not fotos:
        return None
    return fotos[semente % len(fotos)]["largeImageURL"]


def _foto(busca: str, semente: int) -> Image.Image | None:
    """Foto vertical de banco de imagens com licença livre (Pexels ou Pixabay, o que tiver chave).
    Cache local por busca; qualquer falha devolve None (o slide usa o degradê)."""
    provedores = [(n, f, _chave(k)) for n, f, k in (("pexels", _url_pexels, "PEXELS_API_KEY"),
                                                     ("pixabay", _url_pixabay, "PIXABAY_API_KEY"))]
    provedores = [p for p in provedores if p[2]]
    if not provedores or not busca:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    nome = hashlib.sha1(f"{busca}|{semente}".encode()).hexdigest()[:16] + ".jpg"
    if (CACHE / nome).exists():
        return Image.open(CACHE / nome).convert("RGB")
    for _, achar_url, chave in provedores:
        try:
            src = achar_url(busca, semente, chave)
            if not src:
                continue
            with urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"}),
                                        timeout=30) as r:
                (CACHE / nome).write_bytes(r.read())
            return Image.open(CACHE / nome).convert("RGB")
        except Exception:
            continue
    return None


def _fundo(i: int, busca: str, semente: int) -> tuple[Image.Image, bool]:
    foto = _foto(busca, semente)
    if foto is None:
        return _degrade(i), False
    foto = ImageOps.fit(foto, (W, H), Image.LANCZOS)
    # escurece topo e base (legibilidade do texto e das legendas) e aplica um leve tom da marca
    sombra = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        sombra.putpixel((0, y), int(200 * max(0.0, 1 - t / 0.35) ** 1.5 + 230 * max(0.0, (t - 0.55) / 0.45) ** 1.3))
    sombra = sombra.resize((W, H))
    foto = Image.composite(Image.new("RGB", (W, H), (5, 10, 30)), foto, sombra)
    tom = Image.new("RGB", (W, H), PALETA[i % len(PALETA)][0])
    return Image.blend(foto, tom, 0.22), True


# ------------------------------------------------------------------- slides
def _slide(c: dict, idx: int, total: int, destino: Path, marca: str, semente: int) -> bool:
    img, com_foto = _fundo(idx, c.get("imagem", ""), semente + idx)
    img = img.convert("RGBA")
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    d.text((80, 130), marca, font=_fonte(40, False), fill=(255, 255, 255, 230))
    if c["tipo"] == "gancho":
        d.rounded_rectangle((80, 205, 420, 275), 35, fill=DESTAQUE + (255,))
        d.text((110, 215), "VOCÊ SABIA?", font=_fonte(40), fill=(20, 20, 40, 255))

    emoji = (c.get("emoji") or "").strip()
    if emoji:
        try:
            fe = ImageFont.truetype(str(FONTES / "seguiemj.ttf"), 170)
            if com_foto:  # selo circular separa o emoji da foto (rostos, objetos)
                d.ellipse((W // 2 - 150, 560 - 150, W // 2 + 150, 560 + 150), fill=(10, 15, 35, 170),
                          outline=DESTAQUE + (255,), width=6)
            d.text((W // 2, 560), emoji, font=fe, embedded_color=True, anchor="mm")
        except Exception:
            pass

    texto = c["texto"]
    tamanho = 84 if len(texto) < 50 else 72 if len(texto) < 90 else 62
    fonte = _fonte(tamanho)
    linhas = textwrap.wrap(texto, width=max(12, int(1450 / tamanho)))
    alt = int(tamanho * 1.22)
    bloco_h = alt * len(linhas)
    y0 = 760
    d.rounded_rectangle((60, y0 - 40, W - 60, y0 + bloco_h + 30), 36,
                        fill=(10, 15, 35, 150 if com_foto else 90))
    y = y0
    for ln in linhas:
        d.text((W // 2 + 3, y + 3), ln, font=fonte, fill=(0, 0, 0, 180), anchor="ma")
        d.text((W // 2, y), ln, font=fonte, fill=(255, 255, 255, 255), anchor="ma")
        y += alt

    d.rounded_rectangle((80, H - 150, W - 80, H - 136), 7, fill=(255, 255, 255, 70))
    d.rounded_rectangle((80, H - 150, 80 + int((W - 160) * (idx + 1) / total), H - 136), 7, fill=DESTAQUE + (255,))
    if c["tipo"] == "cta":
        d.text((W // 2, H - 220), "Siga para mais automações", font=_fonte(44, False),
               fill=(255, 255, 255, 255), anchor="mm")
    Image.alpha_composite(img, camada).convert("RGB").save(destino, quality=92)
    return com_foto


# ------------------------------------------------------------- narração
async def _tts(texto: str, destino: Path) -> list[tuple[float, float, str]] | None:
    """Gera o MP3 e devolve [(inicio_s, duracao_s, palavra)], ou None sem rede."""
    try:
        import edge_tts
        com = edge_tts.Communicate(texto, VOZ, rate="+6%", boundary="WordBoundary")
        palavras, audio = [], bytearray()
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                palavras.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
        if not audio:
            return None
        destino.write_bytes(bytes(audio))
        return palavras
    except Exception:
        return None


# ---------------------------------------------------------------- legendas
def _ass_tempo(t: float) -> str:
    t = max(0.0, t)
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _fins_de_frase(texto: str, palavras: list[tuple[float, float, str]]) -> set[int]:
    """Índices das palavras seguidas de pontuação no texto falado (a voz não devolve a pontuação)."""
    fins, pos = set(), 0
    for i, (_, _, p) in enumerate(palavras):
        achou = texto.find(p, pos)
        if achou < 0:
            continue
        pos = achou + len(p)
        if pos < len(texto) and texto[pos] in ".,!?;:":
            fins.add(i)
    return fins


def _legendas_ass(eventos: list[tuple[float, float, str, bool]], destino: Path) -> None:
    """Legenda estilo TikTok: grupos de até 3 palavras (quebrando na pontuação), palavra falada em amarelo."""
    cab = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: Leg,Segoe UI Black,94,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,2,"
        "60,60,400,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    linhas, grupos, atual = [], [], []
    for ev in eventos:
        atual.append(ev)
        if len(atual) == 3 or ev[3]:
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    inicios = [ev[0] for ev in eventos]
    n_ev = 0
    for g in grupos:
        for j, (ini, dur, _, _) in enumerate(g):
            fim = g[j + 1][0] if j + 1 < len(g) else ini + max(dur, 0.25) + 0.12
            if n_ev + 1 < len(inicios):          # nunca sobrepõe a próxima legenda
                fim = min(fim, inicios[n_ev + 1])
            n_ev += 1
            partes = []
            for k, (_, _, p, _) in enumerate(g):
                p = p.replace("{", "").replace("}", "").upper()
                partes.append("{\\c&H23B7F7&}" + p + "{\\c&HFFFFFF&}" if k == j else p)
            linhas.append(f"Dialogue: 0,{_ass_tempo(ini)},{_ass_tempo(fim)},Leg,,0,0,0,,{' '.join(partes)}")
    destino.write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ música
def _musica(duracao: float, destino: Path, semente: int) -> None:
    """Trilha ambiente original: pad em progressão vi–IV–I–V + arpejo suave, 96 BPM, normalizada."""
    import numpy as np

    sr = 44100
    n = int(sr * (duracao + 1))
    t = np.arange(n) / sr
    rng = random.Random(semente)
    base = rng.choice([220.0, 233.08, 246.94, 261.63])          # tom varia por vídeo
    semitom = lambda s: base * 2 ** (s / 12)                     # noqa: E731
    acordes = [[9, 12, 16], [5, 9, 12], [0, 4, 7], [7, 11, 14]]  # vi IV I V (relativo ao tom)
    compasso = 4 * 60 / 96
    sinal = np.zeros(n)
    for c in range(int(np.ceil(duracao / compasso)) + 1):
        ini, fim = int(c * compasso * sr), min(n, int((c + 1) * compasso * sr))
        if ini >= n:
            break
        tt = t[ini:fim] - t[ini]
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (compasso - tt) / 0.4)
        for s in acordes[c % 4]:
            f = semitom(s) / 2
            sinal[ini:fim] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * 0.12
        # arpejo: 8 notas por compasso
        passo = compasso / 8
        for k in range(8):
            a = ini + int(k * passo * sr)
            b = min(fim, a + int(0.5 * sr))
            if a >= fim:
                break
            tk = t[a:b] - t[a]
            f = semitom(acordes[c % 4][k % 3] + 12)
            sinal[a:b] += np.exp(-tk * 7) * np.sin(2 * np.pi * f * tk) * 0.10
    sinal[: int(0.8 * sr)] *= np.linspace(0, 1, int(0.8 * sr))
    sinal[-int(1.5 * sr):] *= np.linspace(1, 0, int(1.5 * sr))
    sinal = sinal / (np.abs(sinal).max() + 1e-9) * 0.5
    pcm = (np.repeat(sinal[:, None], 2, axis=1) * 32767).astype(np.int16)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ montagem
def renderizar(roteiro: dict, pasta: Path) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado no PATH")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "roteiro.json").write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
    semente = int(hashlib.sha1(json.dumps(roteiro, sort_keys=True).encode()).hexdigest()[:8], 16)
    marca = roteiro.get("marca") or MARCA

    cenas = [{"texto": roteiro["gancho"], "narracao": roteiro.get("gancho_narracao") or roteiro["gancho"],
              "emoji": roteiro.get("emoji_gancho", "🚨"), "imagem": roteiro.get("imagem_gancho", ""),
              "tipo": "gancho"}]
    cenas += [{**c, "tipo": "cena"} for c in roteiro["cenas"]]
    cenas.append({"texto": roteiro["cta"], "narracao": roteiro["cta"], "emoji": roteiro.get("emoji_cta", "👉"),
                  "imagem": roteiro.get("imagem_cta", ""), "tipo": "cta"})

    segmentos, duracoes, eventos = [], [], []
    com_voz = com_foto = 0
    inicio = 0.0
    for i, c in enumerate(cenas):
        png, mp3, mp4 = pasta / f"s{i:02d}.jpg", pasta / f"s{i:02d}.mp3", pasta / f"s{i:02d}.mp4"
        com_foto += _slide(c, i, len(cenas), png, marca, semente)
        palavras = asyncio.run(_tts(c.get("narracao") or c["texto"], mp3))
        if palavras is not None:
            com_voz += 1
            dur = _duracao(mp3) + 0.45
            audio = ["-i", str(mp3)]
        else:  # sem rede: cena muda, palavras distribuídas igualmente para a legenda
            toks = (c.get("narracao") or c["texto"]).split()
            dur = max(2.5, len(toks) / 2.6)
            palavras = [(k * (dur - 0.4) / len(toks), (dur - 0.4) / len(toks), p) for k, p in enumerate(toks)]
            audio = ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        fins = _fins_de_frase(c.get("narracao") or c["texto"], palavras)
        eventos += [(inicio + a, b, p, k in fins or k == len(palavras) - 1) for k, (a, b, p) in enumerate(palavras)]
        _ffmpeg("-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", str(png), *audio,
                "-vf", f"zoompan=z='min(zoom+0.0007,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                       f":s={W}x{H}:fps={FPS},format=yuv420p",
                "-af", "apad", "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                "-ar", "44100", "-ac", "2", str(mp4))
        segmentos.append(mp4)
        duracoes.append(dur)
        inicio += dur - TRANSICAO

    total = sum(duracoes) - TRANSICAO * (len(duracoes) - 1)
    _legendas_ass(eventos, pasta / "legendas.ass")
    _musica(total, pasta / "musica.wav", semente)

    # Grafo: crossfade de vídeo e áudio entre as cenas, legendas, trilha com sidechain (abaixa na fala).
    entradas: list[str] = []
    for s in segmentos:
        entradas += ["-i", s.name]
    entradas += ["-i", "musica.wav"]
    filtros, v_ant, a_ant, offset = [], "[0:v]", "[0:a]", 0.0
    for k in range(1, len(segmentos)):
        offset += duracoes[k - 1] - TRANSICAO
        filtros.append(f"{v_ant}[{k}:v]xfade=transition=fade:duration={TRANSICAO}:offset={offset:.3f}[v{k}]")
        filtros.append(f"{a_ant}[{k}:a]acrossfade=d={TRANSICAO}[a{k}]")
        v_ant, a_ant = f"[v{k}]", f"[a{k}]"
    m = len(segmentos)
    filtros += [
        f"{v_ant}subtitles=legendas.ass,fade=t=in:st=0:d=0.3,fade=t=out:st={max(total - 0.5, 0):.2f}:d=0.5[vout]",
        f"{a_ant}asplit=2[voz][chave]",
        f"[{m}:a]volume=0.32[trilha]",
        "[trilha][chave]sidechaincompress=threshold=0.03:ratio=9:attack=15:release=350[duck]",
        "[voz][duck]amix=inputs=2:duration=first:normalize=0[aout]",
    ]
    _ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.2f}", "video.mp4",
            cwd=pasta)

    Image.open(pasta / "s00.jpg").save(pasta / "capa.png")
    for arq in list(pasta.glob("s*.*")) + [pasta / "musica.wav"]:
        arq.unlink(missing_ok=True)

    video = pasta / "video.mp4"
    return {"video_path": str(video), "tamanho_bytes": video.stat().st_size,
            "duracao_seg": round(_duracao(video), 2), "cenas": len(cenas), "cenas_com_voz": com_voz,
            "cenas_com_foto": com_foto, "legendas_dinamicas": True, "trilha": True}
