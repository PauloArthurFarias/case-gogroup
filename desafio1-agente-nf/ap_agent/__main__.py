"""CLI: python -m ap_agent [processar|pendencias|vencimentos|exportar] ..."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config, store
from .pipeline import processar_documento, processar_pasta

CORES = {"APROVADO": "\033[32m", "REVISAO": "\033[33m", "REJEITADO": "\033[31m", "ERRO": "\033[35m"}


def _imprimir(r: dict) -> None:
    cor = CORES.get(r["status"], "")
    print(f"{cor}{r['status']:<10}\033[0m {r['arquivo']:<45} {r.get('decidido_por', '')}")
    print(f"           {r['justificativa']}\n")


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="ap_agent", description="Agente de Contas a Pagar")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("processar", help="processa um arquivo ou a pasta inbox/")
    pp.add_argument("caminho", nargs="?", type=Path)
    pp.add_argument("--offline", action="store_true", help="não chama a Claude API")
    sub.add_parser("pendencias", help="lista documentos em revisão")
    pv = sub.add_parser("vencimentos", help="aprovados a pagar nos próximos N dias")
    pv.add_argument("--dias", type=int, default=7)
    pe = sub.add_parser("exportar", help="exporta lançamentos para Excel")
    pe.add_argument("--saida", type=Path, default=config.DATA_DIR / "export" / "lancamentos.xlsx")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if a.cmd == "processar":
        usar_llm = False if a.offline else None
        modo = "Claude API" if (config.llm_disponivel() and not a.offline) else "offline (regras + regex)"
        print(f"Modo: {modo}\n")
        if a.caminho and a.caminho.is_file():
            resultados = [processar_documento(a.caminho, usar_llm)]
        else:
            resultados = processar_pasta(a.caminho, usar_llm)
        for r in resultados:
            _imprimir(r)
        cont = {s: sum(r["status"] == s for r in resultados) for s in ("APROVADO", "REVISAO", "REJEITADO", "ERRO")}
        print("Resumo:", ", ".join(f"{k}={v}" for k, v in cont.items()))
    elif a.cmd == "pendencias":
        with store.conexao() as con:
            for d in store.listar(con, "REVISAO"):
                print(f"#{d['id']:<3} {d['arquivo']:<45} R$ {d['valor_total']:>10.2f}  {d['justificativa']}")
    elif a.cmd == "vencimentos":
        limite = (date.today() + timedelta(days=a.dias)).isoformat()
        with store.conexao() as con:
            for d in store.listar(con, "APROVADO"):
                if d["data_vencimento"] and d["data_vencimento"] <= limite:
                    print(f"{d['data_vencimento']}  R$ {d['valor_total']:>10.2f}  {d['nome_emitente']}  ({d['arquivo']})")
    elif a.cmd == "exportar":
        import pandas as pd
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        with store.conexao() as con:
            df = pd.DataFrame(store.listar(con)).drop(columns=["dados_json", "hash_arquivo"])
        df.to_excel(a.saida, index=False)
        print(f"Exportado: {a.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
