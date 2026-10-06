"""Configura a instância local do n8n a partir do .env do Desafio 2 e reaplica os workflows.

- cria/atualiza as credenciais "OpenRouter" (Header Auth) e "Telegram" (Telegram API) no n8n;
- descobre o chat_id do Telegram pela última mensagem enviada ao bot (mande /start antes);
- grava workflows/src/local.json (fora do git) e chama aplicar_local.py (gera, importa e ativa).

Nenhum segredo é impresso. Uso (com o n8n rodando): python scripts/configurar.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n8n_api import N8n  # noqa: E402

LOCAL = RAIZ / "workflows" / "src" / "local.json"


def ler_env(caminho: Path) -> dict:
    env = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def chat_id_telegram(token: str) -> str | None:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30) as r:
        dados = json.load(r)
    if not dados.get("ok"):
        raise RuntimeError("token do Telegram inválido")
    for upd in reversed(dados.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or {}
        if msg.get("chat", {}).get("id"):
            return str(msg["chat"]["id"])
    return None


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def _versao(modelo: str) -> list[int]:
    return [int(x) if x.isdigit() else 0 for x in modelo.split("-")[1].split(".")]


def _responde(chave: str, modelo: str) -> float | None:
    """Tempo de resposta (s) de uma chamada mínima, ou None se falhar."""
    import time
    corpo = {"model": modelo, "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": 'Responda só {"ok": true}'}]}
    req = urllib.request.Request(f"{GEMINI_URL}/chat/completions", data=json.dumps(corpo).encode(),
                                 headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30):
            return time.time() - t
    except Exception:
        return None


def modelos_gemini(chave: str) -> tuple[str, str]:
    """(principal, reserva): o Flash que respondeu mais rápido agora e o Flash-Lite mais novo.
    Modelos muito novos costumam ficar sobrecarregados (HTTP 503); por isso medimos em vez de pegar o último."""
    padrao = ("gemini-3.5-flash", "gemini-3.5-flash-lite")
    try:
        req = urllib.request.Request(f"{GEMINI_URL}/models", headers={"Authorization": f"Bearer {chave}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = [m["id"].removeprefix("models/") for m in json.load(r).get("data", [])]
    except Exception:
        return padrao
    flash = sorted((i for i in ids if i.startswith("gemini-") and i.endswith("-flash")), key=_versao, reverse=True)
    lite = sorted((i for i in ids if i.startswith("gemini-") and i.endswith("-flash-lite")), key=_versao, reverse=True)
    tempos = {m: t for m in flash[:4] if (t := _responde(chave, m)) is not None}
    principal = min(tempos, key=tempos.get) if tempos else (flash[0] if flash else padrao[0])
    reserva = next((m for m in lite if _responde(chave, m) is not None), lite[0] if lite else padrao[1])
    return principal, reserva


def pexels_ok(chave: str) -> bool:
    try:
        req = urllib.request.Request("https://api.pexels.com/v1/search?query=office&per_page=1",
                                     headers={"Authorization": chave})
        with urllib.request.urlopen(req, timeout=20) as r:
            return bool(json.load(r).get("photos"))
    except Exception:
        return False


def pixabay_ok(chave: str) -> bool:
    try:
        req = urllib.request.Request(f"https://pixabay.com/api/?key={chave}&q=office&per_page=3",
                                     headers={"User-Agent": "Mozilla/5.0"})  # Cloudflare bloqueia o UA padrão
        with urllib.request.urlopen(req, timeout=20) as r:
            return bool(json.load(r).get("hits"))
    except Exception:
        return False


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    env = ler_env(RAIZ / ".env")
    local = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    n = N8n()

    chave_or = env.get("OPENROUTER_API_KEY")
    if not chave_or:  # reaproveita a chave do Desafio 1
        chave_or = ler_env(RAIZ.parent / "desafio1-agente-nf" / ".env").get("AP_LLM_API_KEY", "")
    if chave_or:
        local["openrouter_cred_id"] = n.credencial("OpenRouter", "httpHeaderAuth",
                                                   {"name": "Authorization", "value": f"Bearer {chave_or}"})
        local["modelo_openrouter"] = env.get("OPENROUTER_MODELO") or "nvidia/nemotron-3-super-120b-a12b:free"
        print("OpenRouter: credencial configurada")
    else:
        print("OpenRouter: sem chave (o roteiro virá do banco de roteiros)")

    chave_gm = env.get("GEMINI_API_KEY")
    if chave_gm:
        local["gemini_cred_id"] = n.credencial("Gemini", "httpHeaderAuth",
                                               {"name": "Authorization", "value": f"Bearer {chave_gm}"})
        principal, lite = modelos_gemini(chave_gm)
        local["modelo_gemini"] = env.get("GEMINI_MODELO") or principal
        local["modelo_gemini_lite"] = lite
        print(f"Gemini (reserva): credencial configurada, modelo {local['modelo_gemini']} "
              f"(segunda tentativa: {lite})")
    else:
        print("Gemini (reserva): sem chave")

    chave_px, chave_pb = env.get("PEXELS_API_KEY"), env.get("PIXABAY_API_KEY")
    if chave_px:
        print("Pexels (fotos de fundo):", "chave válida" if pexels_ok(chave_px) else "CHAVE RECUSADA - confira")
    if chave_pb:
        print("Pixabay (fotos de fundo):", "chave válida" if pixabay_ok(chave_pb) else "CHAVE RECUSADA - confira")
    if not (chave_px or chave_pb):
        print("Fotos de fundo: sem chave (fundo em degradê)")

    token_tg = env.get("TELEGRAM_BOT_TOKEN")
    if token_tg:
        chat = chat_id_telegram(token_tg)
        if not chat:
            print("Telegram: nenhuma mensagem recebida pelo bot. Mande /start para ele e rode de novo "
                  "(o resto da configuração segue sem aprovação).")
        else:
            local["telegram_cred_id"] = n.credencial("Telegram", "telegramApi", {"accessToken": token_tg})
            local["telegram_chat_id"] = chat
            local["exigir_aprovacao"] = env.get("EXIGIR_APROVACAO", "true").lower() == "true"
            print(f"Telegram: credencial configurada, chat encontrado, aprovação "
                  f"{'LIGADA' if local['exigir_aprovacao'] else 'desligada'}")
    else:
        print("Telegram: sem token (aprovação humana desligada)")

    if env.get("TIKTOK_CLIENT_KEY") and env.get("TIKTOK_CLIENT_SECRET"):
        local["tiktok_client_key"] = env["TIKTOK_CLIENT_KEY"]
        local["tiktok_client_secret"] = env["TIKTOK_CLIENT_SECRET"]
        if env.get("TIKTOK_REDIRECT_URI"):
            local["tiktok_redirect_uri"] = env["TIKTOK_REDIRECT_URI"]
        real = env.get("TIKTOK_MODO", "simulador").lower() == "real"
        local["tiktok_api_base"] = "https://open.tiktokapis.com" if real else "http://127.0.0.1:8765/mock-tiktok"
        print(f"TikTok: app configurado, modo {'REAL' if real else 'simulador'}")
    else:
        print("TikTok: sem chaves do app (continua no simulador)")

    LOCAL.write_text(json.dumps(local, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "aplicar_local.py")], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
