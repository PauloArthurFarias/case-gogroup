"""Camada de decisão.

1. `decidir_por_regras`: motor determinístico (sempre roda; é o piso de segurança).
2. `decidir_com_agente`: agente Claude com ferramentas de consulta. Ele investiga o caso,
   escreve a justificativa para o analista e sugere a ação (ex.: e-mail ao fornecedor).

Guard-rail: a decisão final é a MAIS RESTRITIVA entre regras e agente. O LLM pode ser mais
cauteloso que as regras, nunca mais permissivo.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from . import cadastros, config, store
from .models import Decisao, DocumentoFiscal, Severidade, Status, Verificacao

log = logging.getLogger(__name__)

_RIGOR = {Status.APROVADO: 0, Status.REVISAO: 1, Status.REJEITADO: 2}


def decidir_por_regras(verificacoes: list[Verificacao]) -> Decisao:
    criticos = [v for v in verificacoes if v.severidade == Severidade.CRITICO]
    alertas = [v for v in verificacoes if v.severidade == Severidade.ALERTA]
    if criticos:
        return Decisao(status=Status.REJEITADO, decidido_por="regras",
                       justificativa="Bloqueado: " + " | ".join(v.mensagem for v in criticos))
    if alertas:
        return Decisao(status=Status.REVISAO, decidido_por="regras",
                       justificativa="Revisão humana: " + " | ".join(v.mensagem for v in alertas))
    prioridade = [v.mensagem for v in verificacoes if v.regra == "vencimento_proximo"]
    return Decisao(status=Status.APROVADO, decidido_por="regras",
                   justificativa="Todas as validações passaram." + (f" {prioridade[0]}" if prioridade else ""))


# ------------------------------------------------------------------ agente
SYSTEM = """Você é o agente de Contas a Pagar de uma indústria. Recebe um documento fiscal já extraído
e o resultado das validações automáticas. Sua função:
1. Investigar o caso com as ferramentas quando houver alerta ou algo incomum (histórico do fornecedor,
   pedido, recebimento).
2. Decidir APROVADO, REVISAO ou REJEITADO chamando `registrar_decisao` exatamente uma vez.
3. Escrever uma justificativa curta e objetiva para o analista financeiro (2 a 4 frases, português) e,
   quando fizer sentido, uma ação sugerida (ex.: texto de e-mail ao fornecedor pedindo carta de correção).

Política: verificação CRITICO => REJEITADO. Verificação ALERTA => no mínimo REVISAO.
Na dúvida, prefira REVISAO. Nunca aprove algo que as regras bloquearam."""

TOOLS = [
    {
        "name": "consultar_pedido",
        "description": "Retorna fornecedor e itens (quantidade, preço unitário) de um pedido de compra.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"pedido": {"type": "string"}},
                         "required": ["pedido"], "additionalProperties": False},
    },
    {
        "name": "consultar_recebimento",
        "description": "Quantidades efetivamente recebidas no almoxarifado para um pedido.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"pedido": {"type": "string"}},
                         "required": ["pedido"], "additionalProperties": False},
    },
    {
        "name": "historico_fornecedor",
        "description": "Cadastro do fornecedor e documentos já processados dele (status e valores).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"cnpj": {"type": "string"}},
                         "required": ["cnpj"], "additionalProperties": False},
    },
    {
        "name": "registrar_decisao",
        "description": "Registra a decisão final sobre o documento. Chame uma única vez, ao final.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["APROVADO", "REVISAO", "REJEITADO"]},
                "justificativa": {"type": "string"},
                "acao_sugerida": {"type": "string"},
            },
            "required": ["status", "justificativa", "acao_sugerida"],
            "additionalProperties": False,
        },
    },
]


def _executar_ferramenta(nome: str, args: dict, con: sqlite3.Connection) -> str:
    if nome == "consultar_pedido":
        return json.dumps(cadastros.pedidos().get(args["pedido"]) or {"erro": "pedido não encontrado"},
                          ensure_ascii=False)
    if nome == "consultar_recebimento":
        return json.dumps(cadastros.recebimentos().get(args["pedido"]) or {"erro": "sem recebimento"},
                          ensure_ascii=False)
    if nome == "historico_fornecedor":
        hist = [{"arquivo": r["arquivo"], "numero": r["numero"], "valor": r["valor_total"], "status": r["status"]}
                for r in store.notas_do_fornecedor(con, args["cnpj"])]
        return json.dumps({"cadastro": cadastros.fornecedores().get(args["cnpj"]), "documentos": hist},
                          ensure_ascii=False)
    return json.dumps({"erro": f"ferramenta desconhecida: {nome}"})


def decidir_com_agente(doc: DocumentoFiscal, verificacoes: list[Verificacao],
                       con: sqlite3.Connection, max_turnos: int = 6) -> Decisao | None:
    """Roda o loop agêntico no provedor configurado. Devolve None se a IA falhar (o chamador usa as regras)."""
    from .llm import provedor_do_processo as provedor

    caso = {
        "documento": doc.model_dump(mode="json"),
        "verificacoes": [v.model_dump(mode="json") for v in verificacoes],
        "decisao_das_regras": decidir_por_regras(verificacoes).model_dump(mode="json"),
    }
    pedido = "Analise o caso abaixo e registre a decisão.\n\n" + json.dumps(caso, ensure_ascii=False, indent=1)
    try:
        r = provedor().rodar_agente(SYSTEM, TOOLS, pedido, lambda nome, args: _executar_ferramenta(nome, args, con),
                                    max_turnos)
    except Exception as e:  # erro inesperado de rede/SDK: nunca derruba o processamento
        log.warning("Agente falhou (%s); usando decisão por regras", e)
        return None
    if not r:
        return None
    acao = r.get("acao_sugerida") or ""
    texto = r["justificativa"] + (f"\nAção sugerida: {acao}" if acao else "")
    return Decisao(status=Status(r["status"]), justificativa=texto, decidido_por=f"agente:{r['modelo']}")


def decidir(doc: DocumentoFiscal, verificacoes: list[Verificacao], con: sqlite3.Connection,
            usar_llm: bool | None = None) -> Decisao:
    regras = decidir_por_regras(verificacoes)
    usar_llm = config.llm_disponivel() if usar_llm is None else usar_llm
    # O agente só investiga exceções: documento limpo não gasta tokens.
    if not usar_llm or regras.status == Status.APROVADO:
        return regras
    agente = decidir_com_agente(doc, verificacoes, con)
    if agente is None:
        return regras
    if _RIGOR[agente.status] < _RIGOR[regras.status]:
        # Guard-rail: o LLM tentou ser mais permissivo que as regras.
        return Decisao(status=regras.status, decidido_por=f"regras (agente sugeriu {agente.status.value})",
                       justificativa=f"{regras.justificativa}\nParecer do agente: {agente.justificativa}")
    return agente
