"""Prepara um ambiente separado para testar o agente com NF-e reais (XML).

Notas reais não estão no cadastro de fornecedores nem têm pedido de compra, então seriam todas
rejeitadas. Este script cria, a partir das próprias notas:
  - o fornecedor (emitente) no cadastro;
  - um pedido de compra e um recebimento com os mesmos itens;
  - um prazo de pagamento para o fornecedor (compras pessoais vêm sem duplicata/vencimento). O prazo
    é fictício, calculado para o vencimento cair 30 dias depois de hoje, e a nota não aparecer vencida;
e copia as notas para uma inbox própria. Tudo fica em `notas_reais/` (fora do git).

Uso:
  python scripts/preparar_notas_reais.py <pasta_com_xmls> [--divergente] [--processar]

  --divergente  pedido com preço 5% MENOR que o da nota: o agente deve mandar para REVISÃO
  --processar   já processa as notas e mostra o resultado (modo offline, sem IA)
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ap_agent import cadastros, config  # noqa: E402
from ap_agent.extract.nfe_xml import extrair_nfe_xml  # noqa: E402

DESTINO = RAIZ / "notas_reais"


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pasta", type=Path)
    p.add_argument("--divergente", action="store_true")
    p.add_argument("--processar", action="store_true")
    a = p.parse_args()

    xmls = sorted(a.pasta.glob("*.xml"))
    if not xmls:
        print(f"Nenhum .xml em {a.pasta}")
        return 1

    data, inbox = DESTINO / "data", DESTINO / "inbox"
    shutil.rmtree(DESTINO, ignore_errors=True)
    data.mkdir(parents=True)
    inbox.mkdir()

    fornecedores, pedidos, recebimentos = {}, [], []
    fator = 0.95 if a.divergente else 1.0
    for i, arq in enumerate(xmls, start=1):
        try:
            doc = extrair_nfe_xml(arq)
        except Exception as e:
            print(f"  ignorado {arq.name}: {e}")
            continue
        shutil.copy(arq, inbox / arq.name)
        prazo = (date.today() - doc.data_emissao).days + 30 if doc.data_emissao else 30
        fornecedores[doc.cnpj_emitente] = (doc.nome_emitente, max(prazo, fornecedores.get(doc.cnpj_emitente, ("", 0))[1]))
        # Se a nota já informa o pedido (xPed), usamos o mesmo número; senão o agente vai inferir.
        num = doc.pedido_compra or f"PC-REAL-{i:03d}"
        for it in doc.itens:
            pedidos.append([num, doc.cnpj_emitente, it.codigo, it.descricao, it.quantidade,
                            round(it.valor_unitario * fator, 4)])
            recebimentos.append([num, it.codigo, it.quantidade])
        print(f"  {arq.name}: {doc.nome_emitente} | {len(doc.itens)} item(ns) | R$ {doc.valor_total:,.2f} | "
              f"pedido na nota: {doc.pedido_compra or 'não informado'} | "
              f"vencimento: {doc.data_vencimento or 'não informado'}")

    with open(data / "fornecedores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cnpj", "razao_social", "categoria", "prazo_pagamento_dias"])
        w.writerows([c, n, "Teste real", prazo] for c, (n, prazo) in fornecedores.items())
    with open(data / "pedidos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pedido", "cnpj_fornecedor", "codigo", "descricao", "quantidade", "valor_unitario"])
        w.writerows(pedidos)
    with open(data / "recebimentos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pedido", "codigo", "quantidade_recebida"])
        w.writerows(recebimentos)

    print(f"\nAmbiente criado em {DESTINO} ({'pedidos 5% abaixo da nota' if a.divergente else 'pedidos iguais às notas'}).")
    print("\nPara usar no PowerShell (painel ou terminal):")
    print(f'  $env:AP_DATA_DIR = "{data}"')
    print(f'  $env:AP_INBOX_DIR = "{inbox}"')
    print("  python -m ap_agent processar      # ou: streamlit run dashboard.py")

    if a.processar:
        config.DATA_DIR, config.INBOX_DIR, config.DB_PATH = data, inbox, data / "contas_a_pagar.db"
        cadastros.recarregar()
        from ap_agent.pipeline import processar_pasta
        print("\nResultado (modo offline):\n")
        for r in processar_pasta(usar_llm=False):
            print(f"  {r['status']:<10} {r['arquivo']}")
            print(f"             {r['justificativa']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
