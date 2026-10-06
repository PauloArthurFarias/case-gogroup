"""Ingestão por e-mail (IMAP): baixa anexos XML/PDF de mensagens não lidas para a inbox.

Funciona com qualquer servidor IMAP. No Gmail, use uma "senha de app" (exige verificação em
duas etapas). As mensagens são marcadas como lidas, nunca apagadas.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path

from . import config, store

log = logging.getLogger(__name__)

EXTENSOES = {".xml", ".pdf"}
TAMANHO_MAX = 10 * 1024 * 1024  # 10 MB por anexo


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:
        return valor


def nome_seguro(nome: str) -> str:
    """Só o nome do arquivo, sem pastas e com caracteres seguros: impede gravar fora da inbox."""
    base = Path(nome.replace("\\", "/")).name
    base = re.sub(r"[^\w.\-]", "_", base, flags=re.ASCII).lstrip(".")
    return base[:120] or "anexo"


def _anexos(msg: Message):
    for parte in msg.walk():
        if parte.get_content_maintype() == "multipart":
            continue
        nome = _decodificar(parte.get_filename())
        if nome:
            yield nome, parte


def buscar_anexos_email(destino: Path | None = None, cliente_imap=None) -> dict:
    """Baixa os anexos XML/PDF das mensagens não lidas.

    Retorna {"emails": [{remetente, assunto, arquivos, ignorados}], "arquivos": [Path, ...]}.
    `cliente_imap` permite injetar um cliente falso nos testes.
    """
    if cliente_imap is None and not config.email_configurado():
        raise RuntimeError("E-mail não configurado: preencha AP_EMAIL_USUARIO e AP_EMAIL_SENHA no .env")
    destino = Path(destino or config.INBOX_DIR)
    destino.mkdir(parents=True, exist_ok=True)

    imap = cliente_imap or imaplib.IMAP4_SSL(config.EMAIL_IMAP_HOST)
    resumo: dict = {"emails": [], "arquivos": []}
    try:
        if cliente_imap is None:
            imap.login(config.EMAIL_USUARIO, config.EMAIL_SENHA)
        imap.select(config.EMAIL_PASTA)
        status, dados = imap.uid("SEARCH", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"busca IMAP falhou: {status}")
        uids = dados[0].split() if dados and dados[0] else []
        for uid in uids:
            uid_txt = uid.decode() if isinstance(uid, bytes) else str(uid)
            status, partes = imap.uid("FETCH", uid_txt, "(BODY.PEEK[])")
            if status != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            msg = email.message_from_bytes(partes[0][1])
            info = {"remetente": _decodificar(msg.get("From")), "assunto": _decodificar(msg.get("Subject")),
                    "arquivos": [], "ignorados": []}
            for nome, parte in _anexos(msg):
                limpo = nome_seguro(nome)
                conteudo = parte.get_payload(decode=True) or b""
                if Path(limpo).suffix.lower() not in EXTENSOES:
                    info["ignorados"].append(f"{limpo} (tipo não aceito)")
                    continue
                if len(conteudo) > TAMANHO_MAX:
                    info["ignorados"].append(f"{limpo} (maior que 10 MB)")
                    continue
                caminho = destino / f"email{uid_txt}_{limpo}"
                caminho.write_bytes(conteudo)
                info["arquivos"].append(caminho.name)
                resumo["arquivos"].append(caminho)
            imap.uid("STORE", uid_txt, "+FLAGS", "(\\Seen)")
            resumo["emails"].append(info)
            with store.conexao() as con:
                store.auditar(con, None, "EMAIL_RECEBIDO",
                              f"de {info['remetente']} | assunto: {info['assunto']} | anexos: "
                              f"{', '.join(info['arquivos']) or 'nenhum'}", "ingestao:email")
            log.info("E-mail %s: %d anexo(s) salvo(s)", uid_txt, len(info["arquivos"]))
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return resumo
