"""Extração de DANFE/boleto em PDF.

Caminho principal: o provedor de IA configurado (ver `llm.py`) devolve um `ExtracaoLLM`
validado pelo schema Pydantic. Com o Claude, o PDF vai inteiro e, se a confiança vier baixa,
a extração é refeita no modelo mais forte.

Sem chave de API (ou se a IA falhar), cai para um extrator por regex sobre o texto do PDF (pypdf). Ele é
propositalmente conservador: confiança 0.6, então o documento sempre passa por revisão humana.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from .. import config
from ..brutils import decodificar_linha_digitavel, so_digitos
from ..models import DocumentoFiscal, ExtracaoLLM, Item, TipoDocumento

log = logging.getLogger(__name__)


def _parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            pass
    return None


def _brl(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", "."))


def _extrair_por_regex(caminho: Path) -> ExtracaoLLM:
    from pypdf import PdfReader

    texto = "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
    cnpjs = re.findall(r"CNPJ:\s*([\d./-]{18})", texto)
    eh_boleto = "Beneficiário" in texto or "Valor do documento" in texto

    if eh_boleto:
        nome = re.search(r"Beneficiário:\s*(.+?)\s+CNPJ", texto)
        valor = re.search(r"Valor do documento:\s*R\$\s*([\d.,]+)", texto)
        venc = re.search(r"Vencimento:\s*(\d{2}/\d{2}/\d{4})", texto)
        linha = re.search(r"(\d{5}\.\d{5} \d{5}\.\d{6} \d{5}\.\d{6} \d \d{14})", texto)
        ref = re.search(r"Ref\.:\s*NF\s*(\d+)", texto)
        return ExtracaoLLM(
            tipo=TipoDocumento.BOLETO, numero=ref.group(1) if ref else None,
            cnpj_emitente=so_digitos(cnpjs[0]) if cnpjs else "",
            nome_emitente=nome.group(1) if nome else "",
            cnpj_destinatario=so_digitos(cnpjs[1]) if len(cnpjs) > 1 else None,
            itens=[], valor_total=_brl(valor.group(1)) if valor else 0.0,
            data_vencimento=_parse_data(venc.group(1)).isoformat() if venc else None,
            linha_digitavel=so_digitos(linha.group(1)) if linha else None,
            confianca=0.6,
        )

    numero = re.search(r"NF-e Nº\s*(\d+)", texto)
    emissao = re.search(r"Emissão:\s*(\d{2}/\d{2}/\d{4})", texto)
    chave = re.search(r"Chave de acesso:\s*([\d ]{54})", texto)
    nome = re.search(r"EMITENTE:\s*(.+?)\s+CNPJ", texto)
    total = re.search(r"VALOR TOTAL DA NOTA:\s*R\$\s*([\d.,]+)", texto)
    prod = re.search(r"VALOR TOTAL DOS PRODUTOS:\s*R\$\s*([\d.,]+)", texto)
    venc = re.search(r"Vencimento\s*(\d{2}/\d{2}/\d{4})", texto)
    pedido = re.search(r"(PC-\d+)", texto)
    itens = [
        Item(codigo=m[0], descricao=m[1].strip(), quantidade=float(m[2]),
             valor_unitario=float(m[3]), valor_total=float(m[4]))
        for m in re.findall(r"^([A-Z]{2,4}-[A-Z0-9]+)\s+(.+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)$", texto, re.M)
    ]
    return ExtracaoLLM(
        tipo=TipoDocumento.DANFE_PDF,
        chave_acesso=so_digitos(chave.group(1)) if chave else None,
        numero=str(int(numero.group(1))) if numero else None, serie="1",
        data_emissao=_parse_data(emissao.group(1)).isoformat() if emissao else None,
        cnpj_emitente=so_digitos(cnpjs[0]) if cnpjs else "",
        nome_emitente=nome.group(1) if nome else "",
        cnpj_destinatario=so_digitos(cnpjs[1]) if len(cnpjs) > 1 else None,
        pedido_compra=pedido.group(1) if pedido else None,
        itens=itens,
        valor_produtos=_brl(prod.group(1)) if prod else None,
        valor_total=_brl(total.group(1)) if total else 0.0,
        data_vencimento=_parse_data(venc.group(1)).isoformat() if venc else None,
        confianca=0.6,
    )


def extrair_pdf(caminho: Path) -> DocumentoFiscal:
    bruto, metodo = None, "regex-offline"
    if config.llm_disponivel():
        from ..llm import provedor
        try:
            bruto, metodo = provedor().extrair_pdf(caminho)
        except Exception as e:  # IA indisponível ou resposta inválida: cai no modo offline
            log.warning("Extração por IA falhou para %s (%s); usando regex", caminho.name, e)
    if bruto is None:
        bruto = _extrair_por_regex(caminho)

    vencimento = _parse_data(bruto.data_vencimento)
    if bruto.tipo == TipoDocumento.BOLETO and bruto.linha_digitavel and not vencimento:
        vencimento = decodificar_linha_digitavel(bruto.linha_digitavel)["vencimento"]

    return DocumentoFiscal(
        tipo=bruto.tipo, arquivo=caminho.name,
        chave_acesso=so_digitos(bruto.chave_acesso) or None,
        numero=bruto.numero, serie=bruto.serie,
        data_emissao=_parse_data(bruto.data_emissao),
        cnpj_emitente=so_digitos(bruto.cnpj_emitente), nome_emitente=bruto.nome_emitente,
        cnpj_destinatario=so_digitos(bruto.cnpj_destinatario) or None,
        pedido_compra=bruto.pedido_compra, itens=bruto.itens,
        valor_produtos=bruto.valor_produtos, valor_total=bruto.valor_total,
        data_vencimento=vencimento,
        linha_digitavel=so_digitos(bruto.linha_digitavel) or None,
        confianca_extracao=bruto.confianca, metodo_extracao=metodo,
    )
