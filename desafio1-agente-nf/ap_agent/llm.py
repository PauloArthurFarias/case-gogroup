"""Provedores de IA, com a mesma interface para o resto do sistema.

- Anthropic (Claude): lê o PDF nativamente e responde em JSON validado (structured outputs).
- OpenAI-compatível (OpenRouter, Ollama...): permite modelos gratuitos como o Qwen. Modelos de texto
  não leem PDF, então o texto é extraído com pypdf e enviado ao modelo.

Quem chama trata exceções: qualquer falha aqui faz o sistema cair no modo offline (regex/regras).
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable

from . import config
from .models import ExtracaoLLM

log = logging.getLogger(__name__)

PROMPT_EXTRACAO = """Você é um analista de contas a pagar. Extraia os dados deste documento fiscal brasileiro
(DANFE de NF-e ou boleto bancário) exatamente como aparecem.

Regras:
- CNPJs, chave de acesso e linha digitável: somente dígitos.
- Datas no formato AAAA-MM-DD. Valores numéricos com ponto decimal (1234.56).
- Em boleto, `cnpj_emitente`/`nome_emitente` são do BENEFICIÁRIO e `itens` fica vazio.
- Procure o número do pedido de compra (ex.: "PC-1005") em dados adicionais/observações.
- Não invente campos ausentes: use null.
- `confianca`: reduza se algum campo estiver ilegível, ambíguo ou se os totais não fecharem."""

ExecutarFerramenta = Callable[[str, dict], str]


def _texto_pdf(caminho: Path) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)


def _cota_esgotada(e: Exception) -> bool:
    """429/RESOURCE_EXHAUSTED: cota do plano gratuito acabou; não adianta tentar de novo neste lote."""
    t = str(e)
    return "429" in t or "RESOURCE_EXHAUSTED" in t or "quota" in t.lower()


def _resumo_erro(e: Exception) -> str:
    t = str(e)
    for chave in ("free-models-per-day", "RESOURCE_EXHAUSTED", "high demand", "UNAVAILABLE"):
        if chave in t:
            return {"free-models-per-day": "cota diária gratuita esgotada (429)",
                    "RESOURCE_EXHAUSTED": "cota diária gratuita esgotada (429)",
                    "high demand": "modelo sobrecarregado (503)", "UNAVAILABLE": "modelo indisponível (503)"}[chave]
    return t[:160]


def _json_de(texto: str) -> str:
    """Remove cercas ```json ... ``` que alguns modelos acrescentam."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("resposta sem JSON")
    return m.group(0)


# ------------------------------------------------------------------ Anthropic
class ProvedorAnthropic:
    nome = "anthropic"

    def _extrair(self, caminho: Path, modelo: str) -> ExtracaoLLM:
        import anthropic

        client = anthropic.Anthropic()
        pdf_b64 = base64.standard_b64encode(caminho.read_bytes()).decode()
        resposta = client.messages.parse(
            model=modelo, max_tokens=4096,
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": PROMPT_EXTRACAO},
            ]}],
            output_format=ExtracaoLLM,
        )
        log.info("Extração %s via %s: %s in / %s out", caminho.name, modelo,
                 resposta.usage.input_tokens, resposta.usage.output_tokens)
        return resposta.parsed_output

    def extrair_pdf(self, caminho: Path) -> tuple[ExtracaoLLM, str]:
        bruto, modelo = self._extrair(caminho, config.MODELO_EXTRACAO), config.MODELO_EXTRACAO
        if bruto.confianca < config.CONFIANCA_MINIMA and config.MODELO_AGENTE != config.MODELO_EXTRACAO:
            log.info("Confiança %.2f baixa, escalando para %s", bruto.confianca, config.MODELO_AGENTE)
            bruto, modelo = self._extrair(caminho, config.MODELO_AGENTE), config.MODELO_AGENTE
        return bruto, f"llm:{modelo}"

    def rodar_agente(self, system: str, tools: list[dict], pedido: str, executar: ExecutarFerramenta,
                     max_turnos: int = 6) -> dict | None:
        import anthropic

        client = anthropic.Anthropic()
        messages: list = [{"role": "user", "content": pedido}]
        try:
            for _ in range(max_turnos):
                resp = client.messages.create(
                    model=config.MODELO_AGENTE, max_tokens=8000, system=system, tools=tools,
                    output_config={"effort": "medium"}, messages=messages,
                )
                # Mantém o conteúdo completo (inclui blocos de thinking) no histórico.
                messages.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason != "tool_use":
                    messages.append({"role": "user", "content": "Finalize chamando registrar_decisao."})
                    continue
                resultados = []
                for bloco in resp.content:
                    if bloco.type != "tool_use":
                        continue
                    if bloco.name == "registrar_decisao":
                        return {**bloco.input, "modelo": config.MODELO_AGENTE}
                    resultados.append({"type": "tool_result", "tool_use_id": bloco.id,
                                       "content": executar(bloco.name, bloco.input)})
                messages.append({"role": "user", "content": resultados})
        except anthropic.APIError as e:
            log.warning("Claude indisponível (%s)", e)
            return None
        log.warning("Agente não concluiu em %d turnos", max_turnos)
        return None


# ------------------------------------------------------- OpenAI-compatível
class ProvedorOpenAICompat:
    """OpenRouter, Gemini (endpoint compatível), Ollama ou qualquer endpoint /v1/chat/completions."""
    nome = "openai_compat"

    def __init__(self, base_url: str | None = None, api_key: str | None = None, modelo: str | None = None):
        self.base_url = base_url or config.LLM_BASE_URL
        self.api_key = api_key or config.LLM_API_KEY
        self.modelo = modelo or config.LLM_MODELO
        self.esgotado = False  # disjuntor: cota acabou, pular até o fim do processo

    def _cliente(self):
        from openai import OpenAI
        return OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=120, max_retries=2)

    def extrair_pdf(self, caminho: Path) -> tuple[ExtracaoLLM, str]:
        texto = _texto_pdf(caminho)
        if len(texto.strip()) < 30:
            raise ValueError("PDF sem texto extraível (provavelmente escaneado)")
        client = self._cliente()
        schema = ExtracaoLLM.model_json_schema()
        mensagens = [
            {"role": "system", "content": PROMPT_EXTRACAO},
            {"role": "user", "content": "Responda SOMENTE com um JSON que siga este schema:\n"
             + json.dumps(schema, ensure_ascii=False) + "\n\nTexto do documento:\n" + texto[:20000]},
        ]
        formatos = [{"type": "json_schema", "json_schema": {"name": "extracao", "schema": schema}},
                    {"type": "json_object"}]
        ultimo_erro: Exception | None = None
        for formato in formatos:  # nem todo modelo gratuito aceita json_schema; tenta o mais simples depois
            try:
                resp = client.chat.completions.create(model=self.modelo, messages=mensagens,
                                                      response_format=formato, temperature=0)
                conteudo = resp.choices[0].message.content
                return ExtracaoLLM.model_validate_json(_json_de(conteudo)), f"llm:{self.modelo}"
            except Exception as e:  # formato não suportado, JSON inválido, cota, 503...
                if _cota_esgotada(e):
                    self.esgotado = True
                    raise RuntimeError(_resumo_erro(e)) from e
                log.info("Extração com %s falhou (%s)", formato["type"], _resumo_erro(e))
                ultimo_erro = e
        raise RuntimeError(_resumo_erro(ultimo_erro) if ultimo_erro else "sem resposta")

    def rodar_agente(self, system: str, tools: list[dict], pedido: str, executar: ExecutarFerramenta,
                     max_turnos: int = 6) -> dict | None:
        from openai import OpenAIError

        client = self._cliente()
        ferramentas = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in tools]
        messages: list = [{"role": "system", "content": system}, {"role": "user", "content": pedido}]
        try:
            for _ in range(max_turnos):
                resp = client.chat.completions.create(model=self.modelo, messages=messages,
                                                      tools=ferramentas, tool_choice="auto", temperature=0)
                msg = resp.choices[0].message
                messages.append(msg.model_dump(exclude_none=True))
                if not msg.tool_calls:
                    messages.append({"role": "user", "content": "Finalize chamando a ferramenta registrar_decisao."})
                    continue
                for chamada in msg.tool_calls:
                    nome = chamada.function.name
                    try:
                        args = json.loads(chamada.function.arguments or "{}")
                    except json.JSONDecodeError:
                        messages.append({"role": "tool", "tool_call_id": chamada.id,
                                         "content": json.dumps({"erro": "argumentos não são JSON válido"})})
                        continue
                    if nome == "registrar_decisao":
                        if args.get("status") in ("APROVADO", "REVISAO", "REJEITADO") and args.get("justificativa"):
                            return {**args, "modelo": self.modelo}
                        messages.append({"role": "tool", "tool_call_id": chamada.id,
                                         "content": json.dumps({"erro": "status inválido ou sem justificativa"})})
                        continue
                    messages.append({"role": "tool", "tool_call_id": chamada.id, "content": executar(nome, args)})
        except OpenAIError as e:
            self.esgotado = self.esgotado or _cota_esgotada(e)
            log.warning("Modelo %s indisponível: %s", self.modelo, _resumo_erro(e))
            return None
        log.warning("Agente não concluiu em %d turnos", max_turnos)
        return None


class ProvedorEmCadeia:
    """Tenta cada provedor em ordem: o primeiro que responder vence (ex.: OpenRouter, depois Gemini)."""
    nome = "cadeia"

    def __init__(self, provedores: list):
        self.provedores = provedores

    def extrair_pdf(self, caminho: Path) -> tuple[ExtracaoLLM, str]:
        ultimo: Exception | None = None
        for p in self.ativos():
            try:
                return p.extrair_pdf(caminho)
            except Exception as e:  # cota esgotada, 503, JSON inválido...: tenta o próximo
                log.warning("IA %s falhou na extração: %s", getattr(p, "modelo", p.nome), e)
                ultimo = e
        raise RuntimeError(f"nenhum provedor de IA respondeu ({ultimo or 'todos com cota esgotada'})")

    def rodar_agente(self, *args, **kwargs) -> dict | None:
        for p in self.ativos():
            r = p.rodar_agente(*args, **kwargs)
            if r:
                return r
        return None

    def ativos(self) -> list:
        return [p for p in self.provedores if not getattr(p, "esgotado", False)]


def provedor():
    """Provedor configurado; com AP_LLM_RESERVA_API_KEY, vira uma cadeia principal -> reserva."""
    cadeia = []
    if config.LLM_PROVEDOR == "openai_compat":
        if config.LLM_API_KEY and config.LLM_MODELO:
            cadeia.append(ProvedorOpenAICompat())
    elif config.ANTHROPIC_API_KEY:
        cadeia.append(ProvedorAnthropic())
    if config.LLM_RESERVA_API_KEY:  # um provedor por modelo: no Gemini gratuito, cada modelo tem cota própria
        for modelo in config.LLM_RESERVA_MODELOS:
            cadeia.append(ProvedorOpenAICompat(config.LLM_RESERVA_BASE_URL, config.LLM_RESERVA_API_KEY, modelo))
    if len(cadeia) == 1:
        return cadeia[0]
    return ProvedorEmCadeia(cadeia or [ProvedorAnthropic()])


_cadeia_do_processo = None
_cadeia_criada_em = 0.0
# Num servidor que fica no ar (painel online), a cadeia é refeita de hora em hora: assim um modelo
# marcado como esgotado volta a ser tentado depois que a cota renova.
VALIDADE_CADEIA_S = 3600


def provedor_do_processo():
    """Mesma cadeia durante o lote, para o disjuntor de cota valer no lote todo."""
    global _cadeia_do_processo, _cadeia_criada_em
    if _cadeia_do_processo is None or time.monotonic() - _cadeia_criada_em > VALIDADE_CADEIA_S:
        _cadeia_do_processo = provedor()
        _cadeia_criada_em = time.monotonic()
    return _cadeia_do_processo
