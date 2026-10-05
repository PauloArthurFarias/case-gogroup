"""Acesso aos dados mestres (fornecedores, pedidos de compra, recebimentos).

Na demo vêm de CSVs. Em produção, esta é a camada que passa a consultar o ERP
(ver docs/plano-implantacao.md); o resto do código não muda.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from . import config


def _ler(nome: str) -> list[dict]:
    caminho: Path = config.DATA_DIR / nome
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache
def fornecedores() -> dict[str, dict]:
    return {r["cnpj"]: r for r in _ler("fornecedores.csv")}


@lru_cache
def pedidos() -> dict[str, dict]:
    """{pedido: {"cnpj_fornecedor": str, "itens": {codigo: {...}}}}"""
    out: dict[str, dict] = {}
    for r in _ler("pedidos.csv"):
        p = out.setdefault(r["pedido"], {"cnpj_fornecedor": r["cnpj_fornecedor"], "itens": {}})
        p["itens"][r["codigo"]] = {
            "descricao": r["descricao"],
            "quantidade": float(r["quantidade"]),
            "valor_unitario": float(r["valor_unitario"]),
        }
    return out


@lru_cache
def recebimentos() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for r in _ler("recebimentos.csv"):
        out[r["pedido"]][r["codigo"]] = float(r["quantidade_recebida"])
    return dict(out)


def recarregar() -> None:
    fornecedores.cache_clear()
    pedidos.cache_clear()
    recebimentos.cache_clear()
