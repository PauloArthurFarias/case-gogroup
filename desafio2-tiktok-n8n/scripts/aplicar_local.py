"""Gera os workflows com a configuração local (workflows/src/local.json), importa no n8n e ativa.

Uso (com o n8n rodando): python scripts/aplicar_local.py
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n8n_api import N8n  # noqa: E402

N8N_CMD = Path.home() / "tools" / "n8n" / "node_modules" / ".bin" / "n8n.cmd"
NODE_DIR = Path.home() / "tools" / "node24"
IDS = ["TikTokErrors0001", "TikTokAuthFlow01", "TikTokPostMain01", "TikTokMcpServer1"]

subprocess.run([sys.executable, str(RAIZ / "workflows" / "src" / "build.py"), "--local"], check=True)
env = {**__import__("os").environ, "PATH": f"{NODE_DIR};" + __import__("os").environ["PATH"]}
r = subprocess.run([str(N8N_CMD), "import:workflow", "--separate", f"--input={RAIZ / 'workflows' / 'local'}"],
                   env=env, capture_output=True, text=True, shell=False)
print((r.stdout + r.stderr).strip().splitlines()[-1])
n = N8n()
for wid in IDS:
    try:
        n.ativar(wid)
        print("ativo:", wid)
    except Exception as e:
        print("FALHA ao ativar", wid, "->", getattr(e, "read", lambda: b"")().decode()[:300] or e)
