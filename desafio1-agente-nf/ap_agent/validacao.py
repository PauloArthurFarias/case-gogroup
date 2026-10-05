"""Regras determinísticas de validação (o "guard-rail" do agente).

Cada regra devolve uma Verificacao com severidade OK / ALERTA / CRITICO.
O LLM nunca pode aprovar um documento que tenha verificação CRITICA (garantido em agente.py).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import cadastros, config, store
from .brutils import chave_acesso_valida, cnpj_valido, decodificar_linha_digitavel, formatar_cnpj
from .models import DocumentoFiscal, Severidade, TipoDocumento, Verificacao

OK, ALERTA, CRITICO = Severidade.OK, Severidade.ALERTA, Severidade.CRITICO


def _v(regra: str, sev: Severidade, msg: str) -> Verificacao:
    return Verificacao(regra=regra, severidade=sev, mensagem=msg)


def validar_cadastrais(doc: DocumentoFiscal) -> list[Verificacao]:
    out = []
    if not cnpj_valido(doc.cnpj_emitente):
        out.append(_v("cnpj_emitente", CRITICO, f"CNPJ {doc.cnpj_emitente} com dígito verificador inválido"))
    forn = cadastros.fornecedores().get(doc.cnpj_emitente)
    if forn:
        out.append(_v("fornecedor_cadastrado", OK, f"Fornecedor {forn['razao_social']} cadastrado"))
    else:
        out.append(_v("fornecedor_cadastrado", CRITICO,
                      f"CNPJ {formatar_cnpj(doc.cnpj_emitente)} ({doc.nome_emitente}) não está no cadastro de fornecedores"))
    if doc.cnpj_destinatario and doc.cnpj_destinatario != config.CNPJ_EMPRESA:
        out.append(_v("destinatario", CRITICO,
                      f"Documento endereçado a outro CNPJ ({formatar_cnpj(doc.cnpj_destinatario)})"))
    return out


def validar_nota(doc: DocumentoFiscal) -> list[Verificacao]:
    out = []
    if doc.tipo == TipoDocumento.NFE_XML or doc.chave_acesso:
        if chave_acesso_valida(doc.chave_acesso):
            out.append(_v("chave_acesso", OK, "Chave de acesso válida (DV mod 11)"))
        else:
            out.append(_v("chave_acesso", CRITICO,
                          "Chave de acesso inválida: dígito verificador não confere (possível adulteração)"))
    soma = round(sum(i.valor_total for i in doc.itens), 2)
    ref = doc.valor_produtos if doc.valor_produtos is not None else doc.valor_total
    if doc.itens and abs(soma - ref) > 0.01:
        out.append(_v("soma_itens", CRITICO, f"Soma dos itens R$ {soma:.2f} difere do total R$ {ref:.2f}"))
    for it in doc.itens:
        if abs(it.quantidade * it.valor_unitario - it.valor_total) > 0.05:
            out.append(_v("calculo_item", ALERTA, f"Item {it.codigo}: qtd × unitário ≠ total"))
    if doc.confianca_extracao < config.CONFIANCA_MINIMA:
        out.append(_v("confianca_extracao", ALERTA,
                      f"Extração com confiança {doc.confianca_extracao:.0%} ({doc.metodo_extracao}): conferir dados"))
    return out


def validar_match_pedido(doc: DocumentoFiscal) -> list[Verificacao]:
    """3-way match: NF × pedido de compra × recebimento físico."""
    out = []
    if not doc.pedido_compra:
        return [_v("pedido", ALERTA, "Nota sem referência a pedido de compra")]
    ped = cadastros.pedidos().get(doc.pedido_compra)
    if not ped:
        return [_v("pedido", CRITICO, f"Pedido {doc.pedido_compra} não encontrado")]
    if ped["cnpj_fornecedor"] != doc.cnpj_emitente:
        out.append(_v("pedido_fornecedor", CRITICO,
                      f"Pedido {doc.pedido_compra} pertence a outro fornecedor"))
    receb = cadastros.recebimentos().get(doc.pedido_compra, {})
    tol = config.TOLERANCIA_PRECO / 100
    problemas = 0
    for it in doc.itens:
        pi = ped["itens"].get(it.codigo)
        if not pi:
            out.append(_v("item_no_pedido", ALERTA, f"Item {it.codigo} não consta no pedido {doc.pedido_compra}"))
            problemas += 1
            continue
        var = (it.valor_unitario - pi["valor_unitario"]) / pi["valor_unitario"]
        if var > tol:
            out.append(_v("preco", ALERTA,
                          f"{it.codigo}: unitário R$ {it.valor_unitario:.2f} está {var:+.1%} acima do pedido "
                          f"(R$ {pi['valor_unitario']:.2f}; tolerância {config.TOLERANCIA_PRECO:.0f}%)"))
            problemas += 1
        if it.quantidade > pi["quantidade"]:
            out.append(_v("quantidade_pedido", ALERTA,
                          f"{it.codigo}: faturado {it.quantidade:g} > pedido {pi['quantidade']:g}"))
            problemas += 1
        recebido = receb.get(it.codigo, 0)
        if it.quantidade > recebido:
            out.append(_v("recebimento", ALERTA,
                          f"{it.codigo}: faturado {it.quantidade:g}, recebido no almoxarifado {recebido:g}"))
            problemas += 1
    if not problemas:
        out.append(_v("3way_match", OK, f"Nota confere com pedido {doc.pedido_compra} e recebimento"))
    return out


def validar_boleto(doc: DocumentoFiscal, con: sqlite3.Connection) -> list[Verificacao]:
    out = []
    # Golpe do boleto: nome de um fornecedor conhecido com CNPJ de outra pessoa.
    homonimo = next((f for c, f in cadastros.fornecedores().items()
                     if c != doc.cnpj_emitente and f["razao_social"].lower() == doc.nome_emitente.lower()), None)
    if homonimo:
        out.append(_v("fraude_beneficiario", CRITICO,
                      f"Beneficiário usa o nome de '{homonimo['razao_social']}', mas o CNPJ "
                      f"{formatar_cnpj(doc.cnpj_emitente)} não é o cadastrado ({formatar_cnpj(homonimo['cnpj'])}): "
                      "suspeita de boleto adulterado"))
    if not doc.linha_digitavel:
        return out + [_v("linha_digitavel", CRITICO, "Linha digitável não encontrada")]
    dec = decodificar_linha_digitavel(doc.linha_digitavel)
    if not dec["valida"]:
        out.append(_v("linha_digitavel", CRITICO, "Linha digitável inválida: " + "; ".join(dec["erros"])))
    else:
        out.append(_v("linha_digitavel", OK, "Dígitos verificadores da linha digitável conferem"))
        if dec["valor"] is not None and abs(dec["valor"] - doc.valor_total) > 0.01:
            out.append(_v("valor_codigo_barras", CRITICO,
                          f"Valor no código de barras R$ {dec['valor']:.2f} ≠ valor impresso R$ {doc.valor_total:.2f}"))
    # o boleto precisa corresponder a uma nota já recebida do mesmo beneficiário
    notas = store.notas_do_fornecedor(con, doc.cnpj_emitente)
    casada = next((n for n in notas if abs((n["valor_total"] or 0) - doc.valor_total) < 0.01), None)
    if casada:
        out.append(_v("boleto_x_nota", OK, f"Corresponde à NF {casada['numero']} ({casada['arquivo']})"))
    else:
        out.append(_v("boleto_x_nota", ALERTA if cadastros.fornecedores().get(doc.cnpj_emitente) else CRITICO,
                      "Nenhuma NF do mesmo beneficiário com este valor: boleto sem lastro"))
    return out


def validar_vencimento(doc: DocumentoFiscal, hoje: date | None = None) -> list[Verificacao]:
    hoje = hoje or date.today()
    if not doc.data_vencimento:
        return [_v("vencimento", ALERTA, "Sem data de vencimento")]
    dias = (doc.data_vencimento - hoje).days
    if dias < 0:
        return [_v("vencimento", ALERTA, f"Vencido há {-dias} dia(s): juros/multa")]
    if dias <= config.DIAS_ALERTA_VENCIMENTO:
        # Não bloqueia: sinaliza prioridade de pagamento.
        return [_v("vencimento_proximo", OK, f"PRIORIDADE: vence em {dias} dia(s) ({doc.data_vencimento:%d/%m})")]
    return [_v("vencimento", OK, f"Vence em {dias} dias")]


def validar_documento(doc: DocumentoFiscal, con: sqlite3.Connection, hash_arquivo: str) -> list[Verificacao]:
    out = validar_cadastrais(doc)
    dup = store.buscar_duplicado(con, doc, hash_arquivo)
    if dup:
        out.append(_v("duplicidade", CRITICO,
                      f"Já lançado como documento #{dup['id']} ({dup['arquivo']}, status {dup['status']}): "
                      "risco de pagamento em duplicidade"))
    if doc.tipo == TipoDocumento.BOLETO:
        out += validar_boleto(doc, con)
    else:
        out += validar_nota(doc)
        out += validar_match_pedido(doc)
    out += validar_vencimento(doc)
    return out
