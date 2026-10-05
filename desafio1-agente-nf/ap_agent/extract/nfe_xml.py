"""Parser determinístico de NF-e (layout 4.00 da SEFAZ). Não usa LLM: o XML é a fonte da verdade."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from ..brutils import so_digitos
from ..models import DocumentoFiscal, Item, TipoDocumento

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


def _txt(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def extrair_nfe_xml(caminho: Path) -> DocumentoFiscal:
    root = ET.parse(caminho).getroot()
    inf = root.find(".//n:infNFe", NS)
    if inf is None:
        raise ValueError("XML não contém infNFe: não parece ser uma NF-e")

    chave = so_digitos(inf.get("Id", "")) or so_digitos(_txt(root, ".//n:protNFe/n:infProt/n:chNFe"))
    itens, pedidos = [], set()
    for det in inf.findall("n:det", NS):
        prod = det.find("n:prod", NS)
        itens.append(Item(
            codigo=_txt(prod, "n:cProd") or "",
            descricao=_txt(prod, "n:xProd") or "",
            quantidade=float(_txt(prod, "n:qCom") or 0),
            valor_unitario=float(_txt(prod, "n:vUnCom") or 0),
            valor_total=float(_txt(prod, "n:vProd") or 0),
        ))
        if ped := _txt(prod, "n:xPed"):
            pedidos.add(ped)

    dh_emi = _txt(inf, "n:ide/n:dhEmi")
    venc = _txt(inf, "n:cobr/n:dup/n:dVenc")
    return DocumentoFiscal(
        tipo=TipoDocumento.NFE_XML,
        arquivo=caminho.name,
        chave_acesso=chave,
        numero=_txt(inf, "n:ide/n:nNF"),
        serie=_txt(inf, "n:ide/n:serie"),
        data_emissao=date.fromisoformat(dh_emi[:10]) if dh_emi else None,
        cnpj_emitente=so_digitos(_txt(inf, "n:emit/n:CNPJ")),
        nome_emitente=_txt(inf, "n:emit/n:xNome") or "",
        cnpj_destinatario=so_digitos(_txt(inf, "n:dest/n:CNPJ")),
        pedido_compra=sorted(pedidos)[0] if pedidos else None,
        itens=itens,
        valor_produtos=float(_txt(inf, "n:total/n:ICMSTot/n:vProd") or 0),
        valor_total=float(_txt(inf, "n:total/n:ICMSTot/n:vNF") or 0),
        data_vencimento=date.fromisoformat(venc) if venc else None,
        confianca_extracao=1.0,
        metodo_extracao="xml",
    )
