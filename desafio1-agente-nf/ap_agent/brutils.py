"""Utilitários de documentos brasileiros: CNPJ, chave de acesso da NF-e e boleto (FEBRABAN)."""
from __future__ import annotations

import re
from datetime import date, timedelta

# Desde 22/02/2025 o fator de vencimento reiniciou em 1000 (regra FEBRABAN).
_BASE_FATOR = date(2025, 2, 22)


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


# ---------------------------------------------------------------- CNPJ
def _dv_cnpj(base: str) -> str:
    def calc(nums: str, pesos: list[int]) -> str:
        r = sum(int(n) * p for n, p in zip(nums, pesos)) % 11
        return "0" if r < 2 else str(11 - r)

    d1 = calc(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = calc(base + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return d1 + d2


def cnpj_valido(cnpj: str | None) -> bool:
    c = so_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    return _dv_cnpj(c[:12]) == c[12:]


def gerar_cnpj(base12: str) -> str:
    return base12 + _dv_cnpj(base12)


def formatar_cnpj(cnpj: str) -> str:
    c = so_digitos(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else cnpj


# ---------------------------------------------------- Chave de acesso NF-e
def _mod11_chave(nums: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(n) * pesos[i % 8] for i, n in enumerate(reversed(nums)))
    dv = 11 - (soma % 11)
    return "0" if dv >= 10 else str(dv)


def chave_acesso_valida(chave: str | None) -> bool:
    c = so_digitos(chave)
    return len(c) == 44 and _mod11_chave(c[:43]) == c[43]


def gerar_chave_acesso(uf: str, aamm: str, cnpj: str, modelo: str, serie: str,
                       numero: str, tp_emis: str = "1", codigo: str = "12345678") -> str:
    base = f"{uf:0>2}{aamm}{cnpj}{modelo:0>2}{serie:0>3}{numero:0>9}{tp_emis}{codigo:0>8}"
    return base + _mod11_chave(base)


# --------------------------------------------------------------- Boleto
def _mod10(nums: str) -> str:
    soma = 0
    for i, n in enumerate(reversed(nums)):
        p = int(n) * (2 if i % 2 == 0 else 1)
        soma += p // 10 + p % 10
    return str((10 - soma % 10) % 10)


def _mod11_boleto(nums: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(n) * pesos[i % 8] for i, n in enumerate(reversed(nums)))
    dv = 11 - (soma % 11)
    return "1" if dv in (0, 10, 11) else str(dv)


def gerar_linha_digitavel(banco: str, vencimento: date, valor: float, campo_livre: str) -> str:
    fator = (vencimento - _BASE_FATOR).days + 1000
    valor_str = f"{round(valor * 100):010d}"
    sem_dv = f"{banco}9{fator:04d}{valor_str}{campo_livre:0>25}"
    dv = _mod11_boleto(sem_dv)
    barras = sem_dv[:4] + dv + sem_dv[4:]
    c1 = barras[0:4] + barras[19:24]
    c2 = barras[24:34]
    c3 = barras[34:44]
    return c1 + _mod10(c1) + c2 + _mod10(c2) + c3 + _mod10(c3) + barras[4] + barras[5:19]


def decodificar_linha_digitavel(linha: str) -> dict:
    """Valida os DVs e devolve {'valida', 'erros', 'valor', 'vencimento'}."""
    d = so_digitos(linha)
    erros: list[str] = []
    if len(d) != 47:
        return {"valida": False, "erros": [f"linha digitável com {len(d)} dígitos (esperado 47)"],
                "valor": None, "vencimento": None}
    c1, c2, c3 = d[0:9], d[10:20], d[21:31]
    for nome, campo, dv in (("campo 1", c1, d[9]), ("campo 2", c2, d[20]), ("campo 3", c3, d[31])):
        if _mod10(campo) != dv:
            erros.append(f"DV do {nome} inválido")
    barras = d[0:4] + d[32] + d[33:47] + d[4:9] + c2 + c3
    if _mod11_boleto(barras[:4] + barras[5:]) != barras[4]:
        erros.append("DV geral do código de barras inválido")
    fator = int(d[33:37])
    valor = int(d[37:47]) / 100
    vencimento = _BASE_FATOR + timedelta(days=fator - 1000) if fator >= 1000 else None
    return {"valida": not erros, "erros": erros, "valor": valor, "vencimento": vencimento}
