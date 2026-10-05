"""Persistência em SQLite: documentos, verificações e trilha de auditoria (append-only)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config
from .models import Decisao, DocumentoFiscal, Status, Verificacao

SCHEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo TEXT NOT NULL,
    hash_arquivo TEXT NOT NULL,
    tipo TEXT NOT NULL,
    chave_acesso TEXT,
    numero TEXT,
    cnpj_emitente TEXT,
    nome_emitente TEXT,
    pedido_compra TEXT,
    valor_total REAL,
    data_vencimento TEXT,
    status TEXT NOT NULL,
    justificativa TEXT,
    decidido_por TEXT,
    metodo_extracao TEXT,
    confianca REAL,
    dados_json TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_doc_chave ON documentos(chave_acesso);
CREATE INDEX IF NOT EXISTS ix_doc_status ON documentos(status);
CREATE TABLE IF NOT EXISTS verificacoes (
    documento_id INTEGER NOT NULL REFERENCES documentos(id),
    regra TEXT NOT NULL,
    severidade TEXT NOT NULL,
    mensagem TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id INTEGER,
    evento TEXT NOT NULL,
    detalhe TEXT,
    usuario TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conexao(db_path: Path | None = None):
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def auditar(con: sqlite3.Connection, documento_id: int | None, evento: str, detalhe: str = "",
            usuario: str = "agente") -> None:
    con.execute("INSERT INTO auditoria (documento_id, evento, detalhe, usuario, ts) VALUES (?,?,?,?,?)",
                (documento_id, evento, detalhe, usuario, _agora()))


def buscar_duplicado(con: sqlite3.Connection, doc: DocumentoFiscal, hash_arquivo: str) -> sqlite3.Row | None:
    """Documento já lançado (não rejeitado) com mesma chave, mesmo emitente+número ou mesmo arquivo."""
    cond, args = ["hash_arquivo = ?"], [hash_arquivo]
    if doc.chave_acesso:
        cond.append("chave_acesso = ?")
        args.append(doc.chave_acesso)
    if doc.numero and doc.tipo != "BOLETO":
        cond.append("(cnpj_emitente = ? AND numero = ? AND tipo != 'BOLETO')")
        args += [doc.cnpj_emitente, doc.numero]
    sql = f"SELECT * FROM documentos WHERE status != 'REJEITADO' AND ({' OR '.join(cond)}) LIMIT 1"
    return con.execute(sql, args).fetchone()


def notas_do_fornecedor(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM documentos WHERE cnpj_emitente = ? AND tipo != 'BOLETO' ORDER BY id", (cnpj,)
    ).fetchall()


def salvar(con: sqlite3.Connection, doc: DocumentoFiscal, hash_arquivo: str,
           verificacoes: list[Verificacao], decisao: Decisao) -> int:
    agora = _agora()
    cur = con.execute(
        """INSERT INTO documentos (arquivo, hash_arquivo, tipo, chave_acesso, numero, cnpj_emitente,
           nome_emitente, pedido_compra, valor_total, data_vencimento, status, justificativa, decidido_por,
           metodo_extracao, confianca, dados_json, criado_em, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (doc.arquivo, hash_arquivo, doc.tipo.value, doc.chave_acesso, doc.numero, doc.cnpj_emitente,
         doc.nome_emitente, doc.pedido_compra, doc.valor_total,
         doc.data_vencimento.isoformat() if doc.data_vencimento else None,
         decisao.status.value, decisao.justificativa, decisao.decidido_por, doc.metodo_extracao,
         doc.confianca_extracao, doc.model_dump_json(), agora, agora))
    doc_id = cur.lastrowid
    con.executemany("INSERT INTO verificacoes VALUES (?,?,?,?)",
                    [(doc_id, v.regra, v.severidade.value, v.mensagem) for v in verificacoes])
    auditar(con, doc_id, "DECISAO", json.dumps(decisao.model_dump(mode="json"), ensure_ascii=False),
            decisao.decidido_por)
    return doc_id


def atualizar_status(con: sqlite3.Connection, doc_id: int, status: Status, justificativa: str,
                     usuario: str) -> bool:
    cur = con.execute("UPDATE documentos SET status=?, justificativa=?, decidido_por=?, atualizado_em=? WHERE id=?",
                      (status.value, justificativa, usuario, _agora(), doc_id))
    if cur.rowcount:
        auditar(con, doc_id, f"STATUS->{status.value}", justificativa, usuario)
    return bool(cur.rowcount)


def listar(con: sqlite3.Connection, status: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM documentos", []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    rows = con.execute(sql + " ORDER BY id", args).fetchall()
    return [dict(r) for r in rows]


def verificacoes_de(con: sqlite3.Connection, doc_id: int) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT regra, severidade, mensagem FROM verificacoes WHERE documento_id = ?", (doc_id,))]
