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


@pytest.fixture(autouse=True)
def sem_credenciais_reais(monkeypatch):
    """Os testes nunca usam o .env do desenvolvedor: nada de chamadas reais a IA ou e-mail."""
    for nome, valor in {"LLM_PROVEDOR": "anthropic", "ANTHROPIC_API_KEY": "", "LLM_API_KEY": "",
                        "LLM_MODELO": "", "LLM_RESERVA_API_KEY": "", "EMAIL_USUARIO": "",
                        "EMAIL_SENHA": ""}.items():
        monkeypatch.setattr(config, nome, valor)
    from ap_agent import llm
    monkeypatch.setattr(llm, "_cadeia_do_processo", None)  # cada teste monta a própria cadeia


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Gera os dados fictícios num diretório temporário e aponta a config para ele."""
    import gerar_dados_ficticios as gen

    data, inbox = tmp_path / "data", tmp_path / "inbox"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "INBOX_DIR", inbox)
    monkeypatch.setattr(config, "DB_PATH", data / "teste.db")
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


# ------------------------------------------------------- e-mail (IMAP)
class _ImapFalso:
    """Imita imaplib.IMAP4_SSL com mensagens em memória."""

    def __init__(self, mensagens: dict[str, bytes]):
        self.mensagens, self.lidas = mensagens, set()

    def select(self, pasta):
        return "OK", [b"2"]

    def uid(self, comando, *args):
        if comando == "SEARCH":
            return "OK", [" ".join(u for u in self.mensagens if u not in self.lidas).encode()]
        if comando == "FETCH":
            return "OK", [(b"1 (BODY[] {n}", self.mensagens[args[0]]), b")"]
        if comando == "STORE":
            self.lidas.add(args[0])
            return "OK", []
        raise AssertionError(comando)

    def logout(self):
        pass


def _email(assunto: str, anexos: list[tuple[str, bytes]]) -> bytes:
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "fornecedor@exemplo.com", "notas@exemplo.com", assunto
    m.set_content("Segue a nota.")
    for nome, dados in anexos:
        m.add_attachment(dados, maintype="application", subtype="octet-stream", filename=nome)
    return m.as_bytes()


def test_ingestao_email_salva_so_xml_e_pdf_e_marca_lido(ambiente):
    from ap_agent.ingest_email import buscar_anexos_email

    _, inbox = ambiente
    xml = (inbox / "nfe_001_aco_ok.xml").read_bytes()
    imap = _ImapFalso({
        "7": _email("NF 1001", [("nota.xml", xml), ("../../boleto.pdf", b"%PDF-1.4 teste")]),
        "8": _email("Fatura", [("virus.exe", b"MZ")]),
    })
    destino = inbox.parent / "inbox_email"
    r = buscar_anexos_email(destino, cliente_imap=imap)

    assert sorted(p.name for p in r["arquivos"]) == ["email7_boleto.pdf", "email7_nota.xml"]
    assert all(p.parent == destino for p in r["arquivos"])  # nome com ../ não escapa da pasta
    assert "virus.exe (tipo não aceito)" in r["emails"][1]["ignorados"]
    assert imap.lidas == {"7", "8"}
    from ap_agent import store
    with store.conexao() as con:
        eventos = [row["evento"] for row in con.execute("SELECT evento FROM auditoria")]
    assert eventos.count("EMAIL_RECEBIDO") == 2


# ------------------------------------------------------ pedido inferido
def test_pedido_inferido_quando_nota_nao_informa(ambiente):
    from ap_agent.validacao import validar_match_pedido

    _, inbox = ambiente
    doc = extrair_nfe_xml(inbox / "nfe_002_embalagens_ok.xml")
    doc.pedido_compra = None
    regras = {v.regra: v for v in validar_match_pedido(doc)}
    assert regras["pedido_inferido"].severidade == Severidade.OK
    assert doc.pedido_compra == "PC-1002" and "3way_match" in regras

    # ambíguo: o fornecedor ACO tem dois pedidos e a nota não tem itens identificáveis
    doc2 = extrair_nfe_xml(inbox / "nfe_001_aco_ok.xml")
    doc2.pedido_compra, doc2.itens = None, []
    (v,) = validar_match_pedido(doc2)
    assert v.regra == "pedido" and v.severidade == Severidade.ALERTA


def test_vencimento_pelo_prazo_padrao_do_fornecedor(monkeypatch):
    from ap_agent.validacao import validar_vencimento

    doc = DocumentoFiscal(tipo=TipoDocumento.NFE_XML, cnpj_emitente="123", valor_total=1,
                          data_emissao=date.today())
    monkeypatch.setattr(cadastros, "fornecedores", lambda: {"123": {"prazo_pagamento_dias": "30"}})
    regras = {v.regra for v in validar_vencimento(doc)}
    assert "vencimento_calculado" in regras and doc.data_vencimento == date.today() + timedelta(days=30)


# ------------------------------------------------- pastas configuráveis
def test_pastas_configuraveis_por_ambiente(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("AP_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("AP_INBOX_DIR", str(tmp_path / "i"))
    try:
        importlib.reload(config)
        assert config.DATA_DIR == tmp_path / "d" and config.INBOX_DIR == tmp_path / "i"
        assert config.DB_PATH == tmp_path / "d" / "contas_a_pagar.db"
    finally:
        monkeypatch.delenv("AP_DATA_DIR")
        monkeypatch.delenv("AP_INBOX_DIR")
        importlib.reload(config)


# ------------------------------------- provedor OpenAI-compatível (Qwen etc.)
def _cliente_openai_falso(roteiro: list):
    from types import SimpleNamespace as NS

    class Completions:
        def create(self, **kw):
            item = roteiro.pop(0)
            if isinstance(item, Exception):
                raise item
            return NS(choices=[NS(message=item)])

    return NS(chat=NS(completions=Completions()))


def test_provedor_openai_extrai_pdf_com_fallback_de_formato(ambiente, monkeypatch):
    import json as _json

    from openai.types.chat import ChatCompletionMessage

    from ap_agent import llm
    from ap_agent.extract.pdf_documento import extrair_pdf

    _, inbox = ambiente
    monkeypatch.setattr(config, "LLM_PROVEDOR", "openai_compat")
    monkeypatch.setattr(config, "LLM_API_KEY", "teste")
    monkeypatch.setattr(config, "LLM_MODELO", "qwen-teste")
    resposta = {"tipo": "DANFE_PDF", "cnpj_emitente": "08333777000180", "nome_emitente": "TransLog",
                "itens": [], "valor_total": 2850.0, "data_vencimento": "2026-12-01", "confianca": 0.95}
    roteiro = [ValueError("json_schema não suportado"),
               ChatCompletionMessage(role="assistant", content="```json\n" + _json.dumps(resposta) + "\n```")]
    monkeypatch.setattr(llm.ProvedorOpenAICompat, "_cliente", lambda self: _cliente_openai_falso(roteiro))

    doc = extrair_pdf(inbox / "danfe_008_frete_somente_pdf.pdf")
    assert doc.metodo_extracao == "llm:qwen-teste" and doc.confianca_extracao == 0.95
    assert doc.valor_total == 2850.0


def test_provedor_openai_loop_do_agente(ambiente, monkeypatch):
    from openai.types.chat import ChatCompletionMessage

    from ap_agent import llm, store
    from ap_agent.validacao import validar_documento

    _, inbox = ambiente
    monkeypatch.setattr(config, "LLM_PROVEDOR", "openai_compat")
    monkeypatch.setattr(config, "LLM_API_KEY", "teste")
    monkeypatch.setattr(config, "LLM_MODELO", "qwen-teste")

    def chamada(id_, nome, args):
        return {"id": id_, "type": "function", "function": {"name": nome, "arguments": args}}

    roteiro = [
        ChatCompletionMessage(role="assistant", content=None,
                              tool_calls=[chamada("c1", "consultar_recebimento", '{"pedido": "PC-1004"}')]),
        ChatCompletionMessage(role="assistant", content=None, tool_calls=[chamada(
            "c2", "registrar_decisao",
            '{"status": "REVISAO", "justificativa": "Faltaram 100 luvas.", "acao_sugerida": "Pedir NF complementar."}')]),
    ]
    monkeypatch.setattr(llm.ProvedorOpenAICompat, "_cliente", lambda self: _cliente_openai_falso(roteiro))

    doc = extrair_nfe_xml(inbox / "nfe_004_epi_qtd_maior_que_recebida.xml")
    with store.conexao() as con:
        d = agente.decidir(doc, validar_documento(doc, con, "h"), con, usar_llm=True)
    assert d.status == Status.REVISAO and d.decidido_por == "agente:qwen-teste"
    assert "Pedir NF complementar" in d.justificativa


def test_cadeia_de_provedores_usa_a_reserva_quando_o_principal_falha(ambiente, monkeypatch):
    from openai.types.chat import ChatCompletionMessage

    from ap_agent import llm
    from ap_agent.extract.pdf_documento import extrair_pdf

    _, inbox = ambiente
    monkeypatch.setattr(config, "LLM_PROVEDOR", "openai_compat")
    monkeypatch.setattr(config, "LLM_API_KEY", "principal")
    monkeypatch.setattr(config, "LLM_MODELO", "modelo-principal")
    monkeypatch.setattr(config, "LLM_RESERVA_API_KEY", "reserva")
    monkeypatch.setattr(config, "LLM_RESERVA_MODELOS", ["modelo-reserva"])
    ok = ChatCompletionMessage(role="assistant", content='{"tipo": "DANFE_PDF", "cnpj_emitente": "08333777000180", '
                               '"nome_emitente": "TransLog", "itens": [], "valor_total": 2850.0, "confianca": 0.95}')

    def cliente(self):
        if self.modelo == "modelo-principal":  # simula cota esgotada (429) em todas as tentativas
            return _cliente_openai_falso([RuntimeError("429 free-models-per-day")] * 2)
        return _cliente_openai_falso([ok])

    monkeypatch.setattr(llm.ProvedorOpenAICompat, "_cliente", cliente)
    doc = extrair_pdf(inbox / "danfe_008_frete_somente_pdf.pdf")
    assert doc.metodo_extracao == "llm:modelo-reserva" and doc.valor_total == 2850.0


def test_disjuntor_pula_modelo_com_cota_esgotada(monkeypatch):
    from ap_agent import llm

    chamadas = []

    class Falso(llm.ProvedorOpenAICompat):
        def extrair_pdf(self, caminho):
            chamadas.append(self.modelo)
            if self.modelo == "a":
                self.esgotado = True
                raise RuntimeError("cota diária gratuita esgotada (429)")
            return "ok", f"llm:{self.modelo}"

    cadeia = llm.ProvedorEmCadeia([Falso("u", "k", "a"), Falso("u", "k", "b")])
    assert cadeia.extrair_pdf(None)[1] == "llm:b"
    assert cadeia.extrair_pdf(None)[1] == "llm:b"
    assert chamadas == ["a", "b", "b"]  # o modelo esgotado não é chamado de novo
