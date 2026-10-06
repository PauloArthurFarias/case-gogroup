"""Orquestração: ingestão -> extração -> validação -> decisão -> persistência."""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from . import agente, config, store
from .extract.nfe_xml import extrair_nfe_xml
from .extract.pdf_documento import extrair_pdf
from .models import DocumentoFiscal, TipoDocumento
from .validacao import validar_documento

log = logging.getLogger(__name__)
EXTENSOES = {".xml", ".pdf"}


def extrair(caminho: Path) -> DocumentoFiscal:
    if caminho.suffix.lower() == ".xml":
        return extrair_nfe_xml(caminho)
    if caminho.suffix.lower() == ".pdf":
        return extrair_pdf(caminho)
    raise ValueError(f"Formato não suportado: {caminho.suffix}")


def _hash(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def processar_documento(caminho: Path, usar_llm: bool | None = None, db_path: Path | None = None) -> dict:
    """Processa um arquivo e devolve um resumo serializável (usado pela CLI, MCP e dashboard)."""
    inicio = time.perf_counter()
    doc = extrair(caminho)
    return _processar_extraido(caminho, doc, usar_llm, db_path, inicio)


def _processar_extraido(caminho: Path, doc: DocumentoFiscal, usar_llm, db_path, inicio: float) -> dict:
    h = _hash(caminho)
    with store.conexao(db_path) as con:
        verificacoes = validar_documento(doc, con, h)
        decisao = agente.decidir(doc, verificacoes, con, usar_llm)
        doc_id = store.salvar(con, doc, h, verificacoes, decisao)
    resumo = {
        "id": doc_id, "arquivo": caminho.name, "tipo": doc.tipo.value,
        "fornecedor": doc.nome_emitente, "valor": doc.valor_total,
        "vencimento": doc.data_vencimento.isoformat() if doc.data_vencimento else None,
        "status": decisao.status.value, "justificativa": decisao.justificativa,
        "decidido_por": decisao.decidido_por, "extracao": doc.metodo_extracao,
        "segundos": round(time.perf_counter() - inicio, 2),
        "verificacoes": [v.model_dump(mode="json") for v in verificacoes],
    }
    log.info("%s -> %s", caminho.name, decisao.status.value)
    return resumo


def processar_emails(usar_llm: bool | None = None, processar: bool = True) -> dict:
    """Busca anexos nos e-mails não lidos e (opcionalmente) processa os arquivos recebidos."""
    from .ingest_email import buscar_anexos_email

    recebido = buscar_anexos_email()
    resultados = processar_pasta(usar_llm=usar_llm, arquivos=recebido["arquivos"]) \
        if processar and recebido["arquivos"] else []
    return {"emails": recebido["emails"], "resultados": resultados}


def arquivos_da_pasta(pasta: Path | None = None) -> list[Path]:
    return sorted(p for p in (pasta or config.INBOX_DIR).iterdir() if p.suffix.lower() in EXTENSOES)


def processar_pasta(pasta: Path | None = None, usar_llm: bool | None = None,
                    db_path: Path | None = None, arquivos: list[Path] | None = None) -> list[dict]:
    """Processa os XML/PDF da pasta (ou a lista `arquivos`). Notas antes de boletos,
    para o boleto encontrar a nota que lhe dá lastro."""
    arquivos = arquivos if arquivos is not None else arquivos_da_pasta(pasta)
    extraidos = []
    for arq in arquivos:
        inicio = time.perf_counter()
        try:
            extraidos.append((arq, extrair(arq), inicio))
        except Exception as e:  # um arquivo ruim não derruba o lote, mas fica registrado para o analista
            log.warning("Falha ao extrair %s: %s", arq.name, e)
            with store.conexao(db_path) as con:
                store.auditar(con, None, "EXTRACAO_FALHOU", f"{arq.name}: {e}", "pipeline")
            extraidos.append((arq, e, inicio))
    extraidos.sort(key=lambda t: isinstance(t[1], DocumentoFiscal) and t[1].tipo == TipoDocumento.BOLETO)

    resultados = []
    for arq, doc, inicio in extraidos:
        if isinstance(doc, Exception):
            resultados.append({"arquivo": arq.name, "status": "ERRO", "justificativa": str(doc)})
            continue
        resultados.append(_processar_extraido(arq, doc, usar_llm, db_path, inicio))
    return resultados
