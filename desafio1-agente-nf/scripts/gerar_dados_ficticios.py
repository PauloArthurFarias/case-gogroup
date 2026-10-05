"""Gera dados 100% fictícios para a demo: cadastro de fornecedores, pedidos de compra,
recebimentos e uma caixa de entrada com NF-e (XML), DANFE (PDF) e boletos (PDF).

Cada documento exercita um cenário do processo de contas a pagar (ver CENARIOS).
Uso: python scripts/gerar_dados_ficticios.py [--limpar]
"""
from __future__ import annotations

import csv
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from ap_agent.brutils import (formatar_cnpj, gerar_chave_acesso, gerar_cnpj,  # noqa: E402
                              gerar_linha_digitavel)
from ap_agent.config import CNPJ_EMPRESA, DATA_DIR, INBOX_DIR  # noqa: E402

HOJE = date.today()
NOME_EMPRESA = "Indústria Exemplo Ltda"

FORNECEDORES = {
    "ACO": (gerar_cnpj("459871230001"), "Aços Horizonte Ltda", "Matéria-prima"),
    "EMB": (gerar_cnpj("301112220001"), "Embalagens Sol Nascente S.A.", "Embalagem"),
    "LUB": (gerar_cnpj("275556660001"), "Lubrificantes Vale Verde ME", "Manutenção"),
    "EPI": (gerar_cnpj("194448880001"), "Segura EPI Distribuidora", "Segurança"),
    "TRP": (gerar_cnpj("083337770001"), "TransLog Fretes Rápidos", "Logística"),
}
CNPJ_DESCONHECIDO = gerar_cnpj("998887770001")

# pedido -> (fornecedor, [(codigo, descricao, qtd, valor_unit)])
PEDIDOS = {
    "PC-1001": ("ACO", [("ACO-1020", "Chapa de aço 1020 3mm", 50, 412.00)]),
    "PC-1002": ("EMB", [("CX-40", "Caixa papelão 40x30", 2000, 3.15), ("FIT-48", "Fita adesiva 48mm", 300, 6.90)]),
    "PC-1003": ("LUB", [("OL-68", "Óleo hidráulico ISO 68 (balde 20L)", 12, 389.00)]),
    "PC-1004": ("EPI", [("LUV-NIT", "Luva nitrílica (par)", 500, 4.20), ("OCL-01", "Óculos de proteção", 100, 18.50)]),
    "PC-1005": ("TRP", [("FRT-SP", "Frete rodoviário SP-Campinas", 1, 2850.00)]),
    "PC-1006": ("ACO", [("ACO-1045", "Barra redonda aço 1045 2pol", 30, 265.00)]),
    "PC-1007": ("EMB", [("PAL-PBR", "Palete PBR", 80, 58.00)]),
}
# pedido -> {codigo: qtd recebida} (recebimento físico registrado no almoxarifado)
RECEBIMENTOS = {
    "PC-1001": {"ACO-1020": 50},
    "PC-1002": {"CX-40": 2000, "FIT-48": 300},
    "PC-1003": {"OL-68": 12},
    "PC-1004": {"LUV-NIT": 400, "OCL-01": 100},   # faltaram 100 luvas
    "PC-1005": {"FRT-SP": 1},
    "PC-1006": {"ACO-1045": 30},
    "PC-1007": {"PAL-PBR": 80},
}

CENARIOS = [
    # (arquivo, descrição do cenário, resultado esperado)
    ("nfe_001_aco_ok.xml", "NF-e correta, bate com pedido e recebimento", "APROVADO"),
    ("nfe_002_embalagens_ok.xml", "NF-e correta com 2 itens", "APROVADO"),
    ("boleto_002_embalagens.pdf", "Boleto da NF 002, beneficiário e valor conferem", "APROVADO"),
    ("nfe_003_lubrificante_preco_acima.xml", "Preço unitário 8% acima do pedido", "REVISAO"),
    ("nfe_004_epi_qtd_maior_que_recebida.xml", "Cobrou 500 luvas, almoxarifado recebeu 400", "REVISAO"),
    ("nfe_005_fornecedor_desconhecido.xml", "CNPJ emitente fora do cadastro de fornecedores", "REJEITADO"),
    ("nfe_006_duplicada_do_001.xml", "Mesma chave de acesso da NF 001 (pagamento em duplicidade)", "REJEITADO"),
    ("nfe_007_chave_invalida.xml", "Chave de acesso com dígito verificador adulterado", "REJEITADO"),
    ("danfe_008_frete_somente_pdf.pdf", "Fornecedor só envia DANFE em PDF (extração por IA; no modo offline vai para REVISAO)", "APROVADO"),
    ("boleto_009_fraude_beneficiario.pdf", "Boleto da NF 010 com CNPJ do beneficiário trocado (golpe do boleto)", "REJEITADO"),
    ("nfe_010_paletes_vence_em_2_dias.xml", "NF-e correta mas com vencimento em 2 dias (prioridade)", "APROVADO"),
]


# ------------------------------------------------------------------ helpers
def _nfe_xml(numero: int, forn: str, pedido: str, itens: list[tuple], venc: date,
             cnpj_emit: str | None = None, chave: str | None = None) -> tuple[str, str]:
    cnpj, nome, _ = FORNECEDORES.get(forn, (None, "Fornecedor Desconhecido Ltda", ""))
    cnpj = cnpj_emit or cnpj
    emissao = HOJE - timedelta(days=5)
    chave = chave or gerar_chave_acesso("35", emissao.strftime("%y%m"), cnpj, "55", "1", str(numero))
    dets, v_prod = [], 0.0
    for i, (cod, desc, qtd, vu) in enumerate(itens, start=1):
        vt = round(qtd * vu, 2)
        v_prod += vt
        dets.append(f"""
      <det nItem="{i}"><prod><cProd>{cod}</cProd><xProd>{escape(desc)}</xProd><NCM>73089090</NCM>
        <CFOP>5101</CFOP><uCom>UN</uCom><qCom>{qtd:.4f}</qCom><vUnCom>{vu:.4f}</vUnCom>
        <vProd>{vt:.2f}</vProd><xPed>{pedido}</xPed></prod>
        <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>{vt:.2f}</vBC><pICMS>18.00</pICMS>
        <vICMS>{vt * 0.18:.2f}</vICMS></ICMS00></ICMS></imposto></det>""")
    v_prod = round(v_prod, 2)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><cUF>35</cUF><natOp>Venda de mercadoria</natOp><mod>55</mod><serie>1</serie>
      <nNF>{numero}</nNF><dhEmi>{emissao.isoformat()}T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
    <emit><CNPJ>{cnpj}</CNPJ><xNome>{escape(nome)}</xNome></emit>
    <dest><CNPJ>{CNPJ_EMPRESA}</CNPJ><xNome>{escape(NOME_EMPRESA)}</xNome></dest>{''.join(dets)}
    <total><ICMSTot><vProd>{v_prod:.2f}</vProd><vICMS>{v_prod * 0.18:.2f}</vICMS><vFrete>0.00</vFrete>
      <vDesc>0.00</vDesc><vNF>{v_prod:.2f}</vNF></ICMSTot></total>
    <cobr><fat><nFat>{numero}</nFat><vOrig>{v_prod:.2f}</vOrig><vLiq>{v_prod:.2f}</vLiq></fat>
      <dup><nDup>001</nDup><dVenc>{venc.isoformat()}</dVenc><vDup>{v_prod:.2f}</vDup></dup></cobr>
    <infAdic><infCpl>Pedido de compra {pedido}. Documento fictício gerado para demonstração.</infCpl></infAdic>
  </infNFe></NFe>
  <protNFe versao="4.00"><infProt><chNFe>{chave}</chNFe><cStat>100</cStat>
    <xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>
</nfeProc>
"""
    return xml, chave


def _danfe_pdf(path: Path, numero: int, forn: str, pedido: str, itens: list[tuple], venc: date) -> None:
    cnpj, nome, _ = FORNECEDORES[forn]
    emissao = HOJE - timedelta(days=3)
    chave = gerar_chave_acesso("35", emissao.strftime("%y%m"), cnpj, "55", "1", str(numero))
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    def linha(txt: str, size: int = 10, dy: int = 16):
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(40, y, txt)
        y -= dy
    linha("DANFE - Documento Auxiliar da Nota Fiscal Eletrônica", 14, 24)
    linha(f"NF-e Nº {numero:09d}   Série 001   Emissão: {emissao.strftime('%d/%m/%Y')}")
    linha(f"Chave de acesso: {' '.join(chave[i:i+4] for i in range(0, 44, 4))}", dy=24)
    linha(f"EMITENTE: {nome}   CNPJ: {formatar_cnpj(cnpj)}")
    linha(f"DESTINATÁRIO: {NOME_EMPRESA}   CNPJ: {formatar_cnpj(CNPJ_EMPRESA)}", dy=24)
    linha("CÓDIGO     DESCRIÇÃO                                   QTD      V.UNIT      V.TOTAL", 9)
    total = 0.0
    for cod, desc, qtd, vu in itens:
        vt = qtd * vu
        total += vt
        linha(f"{cod:<10} {desc:<42} {qtd:>6}  {vu:>10.2f}  {vt:>11.2f}", 9)
    y -= 10
    linha(f"VALOR TOTAL DOS PRODUTOS: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    linha(f"VALOR TOTAL DA NOTA: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 12, 24)
    linha(f"FATURA: Dup 001  Vencimento {venc.strftime('%d/%m/%Y')}")
    linha(f"DADOS ADICIONAIS: Ref. pedido de compra {pedido}. Documento fictício para demonstração.", 9)
    c.save()


def _boleto_pdf(path: Path, beneficiario: str, cnpj_benef: str, valor: float, venc: date,
                ref_nf: str) -> None:
    linha = gerar_linha_digitavel("341", venc, valor, f"{ref_nf:0>10}" + "1" * 15)
    fmt = f"{linha[0:5]}.{linha[5:10]} {linha[10:15]}.{linha[15:21]} {linha[21:26]}.{linha[26:32]} {linha[32]} {linha[33:]}"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Banco Fictício 341-7")
    c.setFont("Helvetica", 11)
    c.drawString(40, 775, fmt)
    rows = [
        f"Beneficiário: {beneficiario}   CNPJ: {formatar_cnpj(cnpj_benef)}",
        f"Pagador: {NOME_EMPRESA}   CNPJ: {formatar_cnpj(CNPJ_EMPRESA)}",
        f"Vencimento: {venc.strftime('%d/%m/%Y')}",
        f"Valor do documento: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"Nosso número / Ref.: NF {ref_nf}",
        "Documento fictício gerado para demonstração.",
    ]
    for i, r in enumerate(rows):
        c.drawString(40, 745 - i * 20, r)
    c.save()


def _total(itens: list[tuple]) -> float:
    return round(sum(q * v for _, _, q, v in itens), 2)


# --------------------------------------------------------------------- main
def main(limpar: bool = False, data_dir: Path = DATA_DIR, inbox_dir: Path = INBOX_DIR) -> None:
    data_dir.mkdir(exist_ok=True)
    if limpar and inbox_dir.exists():
        for f in inbox_dir.iterdir():
            if f.name != ".gitkeep":
                f.unlink()
        db = data_dir / "contas_a_pagar.db"
        if db.exists():
            db.unlink()
        shutil.rmtree(data_dir / "export", ignore_errors=True)
    inbox_dir.mkdir(exist_ok=True)

    with open(data_dir / "fornecedores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cnpj", "razao_social", "categoria"])
        for cnpj, nome, cat in FORNECEDORES.values():
            w.writerow([cnpj, nome, cat])
    with open(data_dir / "pedidos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pedido", "cnpj_fornecedor", "codigo", "descricao", "quantidade", "valor_unitario"])
        for ped, (forn, itens) in PEDIDOS.items():
            for cod, desc, q, vu in itens:
                w.writerow([ped, FORNECEDORES[forn][0], cod, desc, q, vu])
    with open(data_dir / "recebimentos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pedido", "codigo", "quantidade_recebida"])
        for ped, rec in RECEBIMENTOS.items():
            for cod, q in rec.items():
                w.writerow([ped, cod, q])

    venc_padrao = HOJE + timedelta(days=20)
    out = inbox_dir

    xml, chave_001 = _nfe_xml(1001, "ACO", "PC-1001", PEDIDOS["PC-1001"][1], venc_padrao)
    (out / "nfe_001_aco_ok.xml").write_text(xml, encoding="utf-8")

    itens_002 = PEDIDOS["PC-1002"][1]
    xml, _ = _nfe_xml(2002, "EMB", "PC-1002", itens_002, venc_padrao)
    (out / "nfe_002_embalagens_ok.xml").write_text(xml, encoding="utf-8")
    _boleto_pdf(out / "boleto_002_embalagens.pdf", FORNECEDORES["EMB"][1], FORNECEDORES["EMB"][0],
                _total(itens_002), venc_padrao, "2002")

    itens_003 = [("OL-68", "Óleo hidráulico ISO 68 (balde 20L)", 12, 420.12)]  # +8%
    xml, _ = _nfe_xml(3003, "LUB", "PC-1003", itens_003, venc_padrao)
    (out / "nfe_003_lubrificante_preco_acima.xml").write_text(xml, encoding="utf-8")

    xml, _ = _nfe_xml(4004, "EPI", "PC-1004", PEDIDOS["PC-1004"][1], venc_padrao)
    (out / "nfe_004_epi_qtd_maior_que_recebida.xml").write_text(xml, encoding="utf-8")

    xml, _ = _nfe_xml(5005, "XXX", "PC-1006", [("ACO-1045", "Barra redonda aço 1045 2pol", 30, 265.0)],
                      venc_padrao, cnpj_emit=CNPJ_DESCONHECIDO)
    (out / "nfe_005_fornecedor_desconhecido.xml").write_text(xml, encoding="utf-8")

    xml, _ = _nfe_xml(1001, "ACO", "PC-1001", PEDIDOS["PC-1001"][1], venc_padrao, chave=chave_001)
    (out / "nfe_006_duplicada_do_001.xml").write_text(xml, encoding="utf-8")

    chave_ok = gerar_chave_acesso("35", HOJE.strftime("%y%m"), FORNECEDORES["ACO"][0], "55", "1", "7007")
    chave_ruim = chave_ok[:43] + str((int(chave_ok[43]) + 1) % 10)
    xml, _ = _nfe_xml(7007, "ACO", "PC-1006", PEDIDOS["PC-1006"][1], venc_padrao, chave=chave_ruim)
    (out / "nfe_007_chave_invalida.xml").write_text(xml, encoding="utf-8")

    _danfe_pdf(out / "danfe_008_frete_somente_pdf.pdf", 8008, "TRP", "PC-1005", PEDIDOS["PC-1005"][1],
               venc_padrao)

    itens_010 = PEDIDOS["PC-1007"][1]
    venc_curto = HOJE + timedelta(days=2)
    _boleto_pdf(out / "boleto_009_fraude_beneficiario.pdf", "Embalagens Sol Nascente S.A.",
                CNPJ_DESCONHECIDO, _total(itens_010), venc_curto, "10010")
    xml, _ = _nfe_xml(10010, "EMB", "PC-1007", itens_010, venc_curto)
    (out / "nfe_010_paletes_vence_em_2_dias.xml").write_text(xml, encoding="utf-8")

    with open(data_dir / "cenarios_esperados.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "cenario", "status_esperado"])
        w.writerows(CENARIOS)

    print(f"Gerados {len(CENARIOS)} documentos em {out}")


if __name__ == "__main__":
    main(limpar="--limpar" in sys.argv)
