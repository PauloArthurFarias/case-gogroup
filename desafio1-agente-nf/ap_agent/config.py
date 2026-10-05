"""Configuração central, lida de variáveis de ambiente / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
INBOX_DIR = BASE_DIR / "inbox"
DB_PATH = Path(os.getenv("AP_DB_PATH", DATA_DIR / "contas_a_pagar.db"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODELO_EXTRACAO = os.getenv("AP_MODELO_EXTRACAO", "claude-haiku-4-5")
MODELO_AGENTE = os.getenv("AP_MODELO_AGENTE", "claude-sonnet-5-5")

CNPJ_EMPRESA = os.getenv("AP_CNPJ_EMPRESA", "11222333000181")
TOLERANCIA_PRECO = float(os.getenv("AP_TOLERANCIA_PRECO", "2.0"))
DIAS_ALERTA_VENCIMENTO = int(os.getenv("AP_DIAS_ALERTA_VENCIMENTO", "3"))
# Abaixo desta confiança, a extração por LLM é refeita no modelo mais forte e,
# persistindo, o documento vai para revisão humana.
CONFIANCA_MINIMA = float(os.getenv("AP_CONFIANCA_MINIMA", "0.85"))


def llm_disponivel() -> bool:
    return bool(ANTHROPIC_API_KEY)
