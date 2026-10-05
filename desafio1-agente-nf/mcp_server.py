"""Servidor MCP do Agente de Contas a Pagar.

Expõe o agente como ferramentas para qualquer cliente MCP (Claude Code, Claude Desktop,
nó MCP Client do n8n...). O analista pode, em linguagem natural, pedir
"processe as notas novas", "o que está pendente?", "aprove a #4" etc.

Registro no Claude Code:
    claude mcp add contas-a-pagar -- python "<caminho>/mcp_server.py"
Transporte HTTP (para o n8n):
    python mcp_server.py --http   (escuta em http://127.0.0.1:8000/mcp)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from ap_agent import cadastros, config, store  # noqa: E402
from ap_agent.brutils import so_digitos  # noqa: E402
from ap_agent.models import Status  # noqa: E402
from ap_agent.pipeline import arquivos_da_pasta, processar_documento, processar_pasta  # noqa: E402

mcp = MCPServer("contas-a-pagar", instructions="Agente de Contas a Pagar: processa NF-e/boletos, valida contra pedidos e recebimentos e gerencia a fila de revisão.")


def _resumo(d: dict) -> dict:
    return {k: d[k] for k in ("id", "arquivo", "tipo", "nome_emitente", "valor_total", "data_vencimento",
                              "status", "justificativa", "decidido_por")}


@mcp.tool()
def processar_documentos(arquivo: str | None = None) -> list[dict]:
    """Processa documentos fiscais (NF-e XML, DANFE PDF ou boleto PDF).

    Sem `arquivo`, processa todos os arquivos ainda não lançados da caixa de entrada.
    Com `arquivo` (nome dentro da inbox ou caminho absoluto), processa só ele.
    Retorna status (APROVADO/REVISAO/REJEITADO), justificativa e verificações de cada um.
    """
    if arquivo:
        caminho = Path(arquivo)
        if not caminho.is_absolute():
            caminho = config.INBOX_DIR / arquivo
        return [processar_documento(caminho)]
    with store.conexao() as con:
        ja = {r["arquivo"] for r in store.listar(con)}
    return processar_pasta(arquivos=[p for p in arquivos_da_pasta() if p.name not in ja])


@mcp.tool()
def listar_pendencias() -> list[dict]:
    """Documentos aguardando revisão humana, com o motivo."""
    with store.conexao() as con:
        return [_resumo(d) for d in store.listar(con, "REVISAO")]


@mcp.tool()
def listar_documentos(status: str | None = None) -> list[dict]:
    """Lista lançamentos. `status` opcional: APROVADO, REVISAO, REJEITADO ou PAGO."""
    with store.conexao() as con:
        return [_resumo(d) for d in store.listar(con, status.upper() if status else None)]


@mcp.tool()
def detalhar_documento(documento_id: int) -> dict:
    """Todos os dados extraídos e todas as verificações de um documento."""
    import json
    with store.conexao() as con:
        doc = next((d for d in store.listar(con) if d["id"] == documento_id), None)
        if not doc:
            return {"erro": f"documento {documento_id} não encontrado"}
        return {**_resumo(doc), "dados": json.loads(doc["dados_json"]),
                "verificacoes": store.verificacoes_de(con, documento_id)}


@mcp.tool()
def decidir_pendencia(documento_id: int, aprovar: bool, justificativa: str, analista: str) -> dict:
    """Registra a decisão humana sobre um documento em REVISAO (aprovar ou rejeitar).

    Documentos REJEITADOS por regra crítica não podem ser aprovados por aqui.
    A ação fica na trilha de auditoria com o nome do analista.
    """
    with store.conexao() as con:
        doc = next((d for d in store.listar(con) if d["id"] == documento_id), None)
        if not doc:
            return {"ok": False, "erro": "documento não encontrado"}
        if doc["status"] != Status.REVISAO.value:
            return {"ok": False, "erro": f"documento está {doc['status']}, só REVISAO aceita decisão manual"}
        novo = Status.APROVADO if aprovar else Status.REJEITADO
        store.atualizar_status(con, documento_id, novo, justificativa, f"humano:{analista}")
        return {"ok": True, "id": documento_id, "status": novo.value}


@mcp.tool()
def relatorio_vencimentos(dias: int = 7) -> dict:
    """Títulos aprovados que vencem nos próximos `dias` dias, ordenados por data, com total."""
    hoje = date.today()
    limite = (hoje + timedelta(days=dias)).isoformat()
    with store.conexao() as con:
        itens = sorted((d for d in store.listar(con, "APROVADO")
                        if d["data_vencimento"] and d["data_vencimento"] <= limite),
                       key=lambda d: d["data_vencimento"])
    return {"de": hoje.isoformat(), "ate": limite, "total": round(sum(d["valor_total"] for d in itens), 2),
            "titulos": [_resumo(d) for d in itens]}


@mcp.tool()
def consultar_fornecedor(cnpj: str) -> dict:
    """Cadastro de um fornecedor e histórico de documentos dele."""
    c = so_digitos(cnpj)
    with store.conexao() as con:
        hist = [_resumo(dict(r)) for r in store.notas_do_fornecedor(con, c)]
    return {"cadastro": cadastros.fornecedores().get(c), "documentos": hist}


@mcp.resource("contas-a-pagar://kpis")
def kpis() -> str:
    """Indicadores do processo: volume por status e % de processamento automático."""
    with store.conexao() as con:
        docs = store.listar(con)
    total = len(docs) or 1
    por = {s.value: sum(d["status"] == s.value for d in docs) for s in Status}
    auto = sum(d["decidido_por"] and not d["decidido_por"].startswith("humano") for d in docs)
    return (f"Documentos: {len(docs)} | " + ", ".join(f"{k}: {v}" for k, v in por.items())
            + f" | Decididos sem intervenção humana: {auto / total:.0%}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")
