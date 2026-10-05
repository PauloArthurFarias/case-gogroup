import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ap_agent import agente, cadastros, config  # noqa: E402
from ap_agent.brutils import (chave_acesso_valida, cnpj_valido, decodificar_linha_digitavel,  # noqa: E402
                              gerar_chave_acesso, gerar_linha_digitavel)
from ap_agent.extract.nfe_xml import extrair_nfe_xml  # noqa: E402
from ap_agent.models import DocumentoFiscal, Item, Severidade, Status, TipoDocumento, Verificacao  # noqa: E402
from ap_agent.pipeline import processar_pasta  # noqa: E402


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Gera os dados fictícios num diretório temporário e aponta a config para ele."""
    import gerar_dados_ficticios as gen

    data, inbox = tmp_path / "data", tmp_path / "inbox"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "INBOX_DIR", inbox)
    monkeypatch.setattr(config, "DB_PATH", data / "teste.db")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    gen.main(data_dir=data, inbox_dir=inbox)
    cadastros.recarregar()
    yield data, inbox
    cadastros.recarregar()


# ----------------------------------------------------------- utilitários BR
def test_cnpj():
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-82")
    assert not cnpj_valido("00000000000000")


def test_chave_acesso():
    ch = gerar_chave_acesso("35", "2610", "11222333000181", "55", "1", "123")
    assert len(ch) == 44 and chave_acesso_valida(ch)
    assert not chave_acesso_valida(ch[:43] + str((int(ch[43]) + 1) % 10))


def test_linha_digitavel_roundtrip_e_adulteracao():
    venc = date(2026, 12, 15)
    linha = gerar_linha_digitavel("341", venc, 4640.0, "1" * 25)
    dec = decodificar_linha_digitavel(linha)
    assert dec["valida"] and dec["valor"] == 4640.0 and dec["vencimento"] == venc
    # alterar o valor sem recalcular o DV geral deve ser detectado
    adulterada = linha[:37] + "0000999999"
    assert not decodificar_linha_digitavel(adulterada)["valida"]


# ------------------------------------------------------------- extração
def test_parser_xml(ambiente):
    _, inbox = ambiente
    doc = extrair_nfe_xml(inbox / "nfe_002_embalagens_ok.xml")
    assert doc.tipo == TipoDocumento.NFE_XML
    assert doc.pedido_compra == "PC-1002"
    assert len(doc.itens) == 2
    assert doc.valor_total == pytest.approx(8370.0)
    assert chave_acesso_valida(doc.chave_acesso)


# --------------------------------------------------------------- decisão
def _v(sev):
    return Verificacao(regra="x", severidade=sev, mensagem="m")


def test_regras_decisao():
    assert agente.decidir_por_regras([_v(Severidade.OK)]).status == Status.APROVADO
    assert agente.decidir_por_regras([_v(Severidade.OK), _v(Severidade.ALERTA)]).status == Status.REVISAO
    assert agente.decidir_por_regras([_v(Severidade.ALERTA), _v(Severidade.CRITICO)]).status == Status.REJEITADO


def test_guardrail_llm_nao_pode_ser_mais_permissivo(monkeypatch):
    doc = DocumentoFiscal(tipo=TipoDocumento.NFE_XML, cnpj_emitente="1", valor_total=1,
                          itens=[Item(descricao="a", quantidade=1, valor_unitario=1, valor_total=1)])
    monkeypatch.setattr(agente, "decidir_com_agente", lambda *a, **k: agente.Decisao(
        status=Status.APROVADO, justificativa="parece ok", decidido_por="agente:fake"))
    d = agente.decidir(doc, [_v(Severidade.CRITICO)], con=None, usar_llm=True)
    assert d.status == Status.REJEITADO
    assert "agente sugeriu APROVADO" in d.decidido_por


def test_vencimento_proximo_nao_bloqueia():
    from ap_agent.validacao import validar_vencimento
    doc = DocumentoFiscal(tipo=TipoDocumento.NFE_XML, cnpj_emitente="1", valor_total=1,
                          data_vencimento=date.today() + timedelta(days=1))
    (v,) = validar_vencimento(doc)
    assert v.severidade == Severidade.OK and "PRIORIDADE" in v.mensagem


# ------------------------------------------------------- ponta a ponta
def test_ponta_a_ponta_offline(ambiente):
    data, _ = ambiente
    with open(data / "cenarios_esperados.csv", encoding="utf-8") as f:
        esperado = {r["arquivo"]: r["status_esperado"] for r in csv.DictReader(f)}
    # sem LLM, a DANFE em PDF é extraída por regex com confiança baixa -> revisão humana
    esperado["danfe_008_frete_somente_pdf.pdf"] = "REVISAO"

    resultados = {r["arquivo"]: r for r in processar_pasta(usar_llm=False)}
    assert set(resultados) == set(esperado)
    divergentes = {a: (resultados[a]["status"], s) for a, s in esperado.items() if resultados[a]["status"] != s}
    assert not divergentes, divergentes


def test_reprocessar_e_bloqueado_como_duplicado(ambiente):
    processar_pasta(usar_llm=False)
    segunda = processar_pasta(usar_llm=False)
    aprovados_antes = [r for r in segunda if r["arquivo"].startswith("nfe_001")]
    assert aprovados_antes[0]["status"] == "REJEITADO"
    assert "duplicidade" in aprovados_antes[0]["justificativa"]


def test_loop_do_agente_com_cliente_simulado(ambiente, monkeypatch):
    """Exercita o loop agêntico (tool_use -> tool_result -> decisão) sem chamar a API."""
    from types import SimpleNamespace as NS

    import anthropic

    from ap_agent import store
    from ap_agent.validacao import validar_documento

    _, inbox = ambiente
    roteiro = [
        NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="consultar_recebimento",
                                               input={"pedido": "PC-1004"})]),
        NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t2", name="registrar_decisao",
                                               input={"status": "REVISAO", "justificativa": "Faltaram 100 luvas.",
                                                      "acao_sugerida": "Pedir NF complementar."})]),
    ]
    enviados = []

    class FakeMessages:
        def create(self, **kw):
            enviados.append(kw["messages"][-1])
            return roteiro.pop(0)

    monkeypatch.setattr(anthropic, "Anthropic", lambda: NS(messages=FakeMessages()))
    doc = extrair_nfe_xml(inbox / "nfe_004_epi_qtd_maior_que_recebida.xml")
    with store.conexao() as con:
        verif = validar_documento(doc, con, "hash")
        d = agente.decidir(doc, verif, con, usar_llm=True)
    assert d.status == Status.REVISAO and d.decidido_por.startswith("agente:")
    assert "Pedir NF complementar" in d.justificativa
    resultado_ferramenta = enviados[1]["content"][0]
    assert resultado_ferramenta["type"] == "tool_result" and "LUV-NIT" in resultado_ferramenta["content"]
