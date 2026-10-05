"""Renderiza um roteiro em vídeo vertical 1080x1920 (formato TikTok).

Cada cena vira um slide (Pillow) com narração (edge-tts, voz neural pt-BR gratuita).
O ffmpeg junta tudo em MP4 H.264/AAC. Sem internet para o TTS, a cena fica muda e com
duração proporcional ao texto: o vídeo sai mesmo assim.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
VOZ = "pt-BR-AntonioNeural"
FONTES = Path("C:/Windows/Fonts")
PALETA = [((14, 30, 74), (37, 87, 167)), ((20, 20, 40), (90, 40, 140)), ((8, 60, 70), (20, 130, 120))]
DESTAQUE = (247, 168, 35)
MARCA = "@automacao.na.pratica"


def _fonte(tamanho: int, negrito: bool = True) -> ImageFont.FreeTypeFont:
    for nome in (("segoeuib.ttf", "arialbd.ttf") if negrito else ("segoeui.ttf", "arial.ttf")):
        if (FONTES / nome).exists():
            return ImageFont.truetype(str(FONTES / nome), tamanho)
    return ImageFont.load_default(tamanho)


def _fundo(i: int) -> Image.Image:
    topo, base = PALETA[i % len(PALETA)]
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / H
        grad.putpixel((0, y), tuple(int(topo[c] * (1 - t) + base[c] * t) for c in range(3)))
    img = grad.resize((W, H))
    # brilho decorativo
    luz = Image.new("L", (W, H), 0)
    ImageDraw.Draw(luz).ellipse((W - 700, -300, W + 300, 700), fill=90)
    luz = luz.filter(ImageFilter.GaussianBlur(160))
    return Image.composite(Image.new("RGB", (W, H), DESTAQUE), img, luz.point(lambda v: v // 3))


def _slide(texto: str, idx: int, total: int, tipo: str, destino: Path, marca: str = MARCA) -> None:
    img = _fundo(idx)
    d = ImageDraw.Draw(img)
    d.text((80, 140), marca, font=_fonte(40, False), fill=(255, 255, 255))
    if tipo == "gancho":
        d.rounded_rectangle((80, 230, 420, 300), 35, fill=DESTAQUE)
        d.text((110, 240), "VOCÊ SABIA?", font=_fonte(40), fill=(20, 20, 40))
    tamanho = 92 if len(texto) < 60 else 76 if len(texto) < 110 else 64
    fonte = _fonte(tamanho)
    linhas = textwrap.wrap(texto, width=int(1500 / tamanho))
    alt_linha = int(tamanho * 1.25)
    y = (H - alt_linha * len(linhas)) // 2
    for ln in linhas:
        larg = d.textlength(ln, font=fonte)
        x = (W - larg) // 2
        d.text((x + 4, y + 4), ln, font=fonte, fill=(0, 0, 0))
        d.text((x, y), ln, font=fonte, fill=(255, 255, 255))
        y += alt_linha
    # barra de progresso
    d.rounded_rectangle((80, H - 200, W - 80, H - 184), 8, fill=(255, 255, 255, 60))
    d.rounded_rectangle((80, H - 200, 80 + int((W - 160) * (idx + 1) / total), H - 184), 8, fill=DESTAQUE)
    if tipo == "cta":
        d.text((W // 2, H - 300), "Siga para mais automações", font=_fonte(44, False),
               fill=(255, 255, 255), anchor="mm")
    img.save(destino)


async def _tts(texto: str, destino: Path) -> bool:
    try:
        import edge_tts
        await edge_tts.Communicate(texto, VOZ, rate="+6%").save(str(destino))
        return destino.exists() and destino.stat().st_size > 0
    except Exception:
        return False


def _duracao(arq: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(arq)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def _ffmpeg(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg falhou: {r.stderr[-500:]}")


def renderizar(roteiro: dict, pasta: Path) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado no PATH")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "roteiro.json").write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")

    cenas = [{"texto": roteiro["gancho"], "narracao": roteiro.get("gancho_narracao") or roteiro["gancho"],
              "tipo": "gancho"}]
    cenas += [{**c, "tipo": "cena"} for c in roteiro["cenas"]]
    cenas.append({"texto": roteiro["cta"], "narracao": roteiro["cta"], "tipo": "cta"})

    segmentos, com_voz = [], 0
    for i, c in enumerate(cenas):
        png, mp3, mp4 = pasta / f"s{i:02d}.png", pasta / f"s{i:02d}.mp3", pasta / f"s{i:02d}.mp4"
        _slide(c["texto"], i, len(cenas), c["tipo"], png, roteiro.get("marca") or MARCA)
        if asyncio.run(_tts(c.get("narracao") or c["texto"], mp3)):
            com_voz += 1
            dur = _duracao(mp3) + 0.35
            audio = ["-i", str(mp3)]
        else:
            dur = max(2.5, len(c["texto"].split()) / 2.6)
            audio = ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        fade_out = max(dur - 0.25, 0)
        _ffmpeg("-loop", "1", "-framerate", "30", "-t", f"{dur:.2f}", "-i", str(png), *audio,
                "-vf", f"zoompan=z='min(zoom+0.0006,1.06)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,"
                       f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.2f}:d=0.25,format=yuv420p",
                "-af", "apad", "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k",
                "-ar", "44100", "-ac", "2", str(mp4))
        segmentos.append(mp4)

    lista = pasta / "concat.txt"
    lista.write_text("".join(f"file '{s.name}'\n" for s in segmentos), encoding="utf-8")
    video = pasta / "video.mp4"
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(video))
    shutil.copy(pasta / "s00.png", pasta / "capa.png")
    for arq in pasta.glob("s*.*"):
        arq.unlink()
    lista.unlink()

    return {"video_path": str(video), "tamanho_bytes": video.stat().st_size,
            "duracao_seg": round(_duracao(video), 2), "cenas": len(cenas), "cenas_com_voz": com_voz}
