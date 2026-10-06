"""Configuração central, lida de variáveis de ambiente / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Pastas configuráveis: permitem rodar um ambiente separado (ex.: notas reais) sem misturar com a demo.
DATA_DIR = Path(os.getenv("AP_DATA_DIR") or BASE_DIR / "data")
INBOX_DIR = Path(os.getenv("AP_INBOX_DIR") or BASE_DIR / "inbox")
DB_PATH = Path(os.getenv("AP_DB_PATH") or DATA_DIR / "contas_a_pagar.db")

# Provedor de IA: "anthropic" (Claude) ou "openai_compat" (qualquer API compatível com OpenAI:
# OpenRouter, Ollama, etc.). Sem chave, o agente roda em modo offline.
LLM_PROVEDOR = os.getenv("AP_LLM_PROVEDOR", "anthropic").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODELO_EXTRACAO = os.getenv("AP_MODELO_EXTRACAO", "claude-haiku-4-5")
MODELO_AGENTE = os.getenv("AP_MODELO_AGENTE", "claude-sonnet-5-5")
LLM_BASE_URL = os.getenv("AP_LLM_BASE_URL", "https://openrouter.ai/api/v1").strip()
LLM_API_KEY = os.getenv("AP_LLM_API_KEY", "").strip()
LLM_MODELO = os.getenv("AP_LLM_MODELO", "").strip()

CNPJ_EMPRESA = os.getenv("AP_CNPJ_EMPRESA", "11222333000181")
TOLERANCIA_PRECO = float(os.getenv("AP_TOLERANCIA_PRECO", "2.0"))
DIAS_ALERTA_VENCIMENTO = int(os.getenv("AP_DIAS_ALERTA_VENCIMENTO", "3"))
# Abaixo desta confiança, a extração por LLM é refeita no modelo mais forte e,
# persistindo, o documento vai para revisão humana.
CONFIANCA_MINIMA = float(os.getenv("AP_CONFIANCA_MINIMA", "0.85"))

# Caixa de e-mail (IMAP) de onde chegam as notas.
EMAIL_IMAP_HOST = os.getenv("AP_EMAIL_IMAP_HOST", "imap.gmail.com").strip()
EMAIL_USUARIO = os.getenv("AP_EMAIL_USUARIO", "").strip()
EMAIL_SENHA = os.getenv("AP_EMAIL_SENHA", "").replace(" ", "").strip()
EMAIL_PASTA = os.getenv("AP_EMAIL_PASTA", "INBOX").strip()


def llm_disponivel() -> bool:
    if LLM_PROVEDOR == "openai_compat":
        return bool(LLM_API_KEY and LLM_MODELO)
    return bool(ANTHROPIC_API_KEY)


def descricao_llm() -> str:
    if not llm_disponivel():
        return "offline (regras + regex)"
    if LLM_PROVEDOR == "openai_compat":
        return f"{LLM_MODELO} via {LLM_BASE_URL}"
    return f"Claude API ({MODELO_EXTRACAO} / {MODELO_AGENTE})"


def email_configurado() -> bool:
    return bool(EMAIL_USUARIO and EMAIL_SENHA)
