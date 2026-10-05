"""Serviço de mídia local chamado pelo n8n (HTTP Request).

Endpoints:
  GET  /health
  POST /render                   roteiro JSON -> vídeo 9:16 (TTS + slides + ffmpeg)
  GET  /videos/<id>/<arquivo>    serve o vídeo/capa gerados
  GET|POST /tokens               guarda os tokens OAuth do TikTok (arquivo local, fora do git)
  GET|POST /log                  histórico de publicações (CSV)
  /mock-tiktok/...               simulador da TikTok Content Posting API (mesmos contratos)
                                 para testar o fluxo sem app aprovado

Executar: python media_service/server.py  (porta 8765)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import renderizar  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "output"
TOKENS = BASE / "tokens.json"
LOG = OUTPUT / "publicacoes.csv"
MOCK = OUTPUT / "mock_tiktok"
PORTA = 8765
_lock = threading.Lock()
_mock_posts: dict[str, dict] = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "MediaService/1.0"

    # ------------------------------------------------------------ helpers
    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _body_json(self) -> dict:
        raw = self._body()
        return json.loads(raw) if raw else {}

    def log_message(self, fmt, *args):  # log enxuto
        sys.stderr.write(f"[{datetime.now():%H:%M:%S}] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")

    # --------------------------------------------------------------- GET
    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if m := re.fullmatch(r"/videos/([\w-]+)/([\w.-]+)", self.path):
            arq = OUTPUT / m.group(1) / m.group(2)
            if not arq.is_file():
                return self._json(404, {"erro": "não encontrado"})
            data = arq.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4" if arq.suffix == ".mp4" else "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        if self.path == "/tokens":
            return self._json(200, json.loads(TOKENS.read_text()) if TOKENS.exists() else {})
        if self.path == "/log":
            if not LOG.exists():
                return self._json(200, [])
            with open(LOG, encoding="utf-8") as f:
                return self._json(200, list(csv.DictReader(f)))
        return self._json(404, {"erro": "rota inexistente"})

    # -------------------------------------------------------------- POST
    def do_POST(self):
        if self.path == "/render":
            roteiro = self._body_json()
            vid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
            try:
                info = renderizar(roteiro, OUTPUT / vid)
            except Exception as e:  # devolve o erro para o n8n tratar
                return self._json(500, {"erro": str(e)})
            base = f"http://127.0.0.1:{PORTA}/videos/{vid}"
            return self._json(200, {"id": vid, **info, "video_url": f"{base}/video.mp4",
                                    "capa_url": f"{base}/capa.png"})
        if self.path == "/tokens":
            dados = self._body_json()
            if "expires_in" in dados:
                dados["expira_em"] = int(time.time()) + int(dados["expires_in"])
            if "refresh_expires_in" in dados:
                dados["refresh_expira_em"] = int(time.time()) + int(dados["refresh_expires_in"])
            TOKENS.write_text(json.dumps(dados, indent=2))
            return self._json(200, {"ok": True, "expira_em": dados.get("expira_em")})
        if self.path == "/log":
            reg = self._body_json()
            campos = ["data", "tema", "titulo", "publish_id", "status", "privacidade", "video", "modo", "erro"]
            OUTPUT.mkdir(exist_ok=True)
            with _lock:
                novo = not LOG.exists()
                with open(LOG, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
                    if novo:
                        w.writeheader()
                    w.writerow({"data": datetime.now().isoformat(timespec="seconds"), **reg})
            return self._json(200, {"ok": True})
        if self.path.startswith("/mock-tiktok/"):
            return self._mock_post(self.path.removeprefix("/mock-tiktok"))
        return self._json(404, {"erro": "rota inexistente"})

    def do_PUT(self):
        if m := re.fullmatch(r"/mock-tiktok/upload/([\w-]+)", self.path):
            post = _mock_posts.get(m.group(1))
            if not post:
                return self._json(404, {"erro": "upload_url inválida"})
            dados = self._body()
            esperado = post["video_size"]
            faixa = self.headers.get("Content-Range", "")
            if len(dados) != esperado or not faixa.startswith(f"bytes 0-{esperado - 1}/{esperado}"):
                post["status"] = "FAILED"
                post["fail_reason"] = "file_format_check_failed"
                return self._json(400, {"erro": "tamanho/Content-Range não conferem"})
            MOCK.mkdir(parents=True, exist_ok=True)
            (MOCK / f"{m.group(1)}.mp4").write_bytes(dados)
            post["status"] = "PROCESSING_UPLOAD"
            post["upload_em"] = time.time()
            self.send_response(201)
            self.end_headers()
            return None
        return self._json(404, {"erro": "rota inexistente"})

    # ---------------------------------------------- simulador TikTok API
    def _mock_ok(self, data: dict):
        return self._json(200, {"data": data, "error": {"code": "ok", "message": "", "log_id": uuid.uuid4().hex}})

    def _mock_post(self, rota: str):
        auth = self.headers.get("Authorization", "")
        if rota == "/v2/oauth/token/":
            corpo = self._body().decode()
            if "grant_type=" not in corpo:
                return self._json(400, {"error": "invalid_request"})
            return self._json(200, {"access_token": "act.mock" + uuid.uuid4().hex, "expires_in": 86400,
                                    "refresh_token": "rft.mock" + uuid.uuid4().hex,
                                    "refresh_expires_in": 31536000, "open_id": "mock-open-id",
                                    "scope": "user.info.basic,video.publish", "token_type": "Bearer"})
        if not auth.startswith("Bearer "):
            return self._json(401, {"error": {"code": "access_token_invalid", "message": "sem token"}})
        corpo = self._body_json()
        if rota == "/v2/post/publish/creator_info/query/":
            return self._mock_ok({"creator_nickname": "conta_de_teste", "creator_username": "conta.teste",
                                  "privacy_level_options": ["SELF_ONLY"], "comment_disabled": False,
                                  "duet_disabled": False, "stitch_disabled": True,
                                  "max_video_post_duration_sec": 600})
        if rota == "/v2/post/publish/video/init/":
            src = corpo.get("source_info", {})
            if src.get("source") != "FILE_UPLOAD" or src.get("total_chunk_count") != 1:
                return self._json(400, {"error": {"code": "invalid_params", "message": "source_info inválido"}})
            if corpo.get("post_info", {}).get("privacy_level") not in ("SELF_ONLY",):
                return self._json(403, {"error": {"code": "unaudited_client_can_only_post_to_private_accounts",
                                                  "message": "app não auditado: use SELF_ONLY"}})
            pid = "v_pub_mock_" + uuid.uuid4().hex[:12]
            _mock_posts[pid] = {"video_size": src["video_size"], "status": "PROCESSING_UPLOAD",
                                "post_info": corpo["post_info"]}
            return self._mock_ok({"publish_id": pid,
                                  "upload_url": f"http://127.0.0.1:{PORTA}/mock-tiktok/upload/{pid}"})
        if rota == "/v2/post/publish/status/fetch/":
            post = _mock_posts.get(corpo.get("publish_id", ""))
            if not post:
                return self._json(404, {"error": {"code": "invalid_publish_id", "message": ""}})
            # simula o processamento do TikTok: conclui ~3 s depois do upload
            if post["status"] == "PROCESSING_UPLOAD" and post.get("upload_em") and time.time() - post["upload_em"] > 3:
                post["status"] = "PUBLISH_COMPLETE"
            return self._mock_ok({"status": post["status"], "fail_reason": post.get("fail_reason", ""),
                                  "publicaly_available_post_id": []})
        return self._json(404, {"error": {"code": "not_found", "message": rota}})


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    print(f"Serviço de mídia em http://127.0.0.1:{PORTA}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
