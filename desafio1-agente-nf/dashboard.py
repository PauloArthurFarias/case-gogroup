"""Painel do analista: KPIs, fila de revisão, vencimentos e upload manual.

Executar: streamlit run dashboard.py
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ap_agent import config, store  # noqa: E402
from ap_agent.models import Status  # noqa: E402
from ap_agent.pipeline import arquivos_da_pasta, processar_documento, processar_pasta  # noqa: E402

st.set_page_config(page_title="Agente de Contas a Pagar", page_icon="🧾", layout="wide")
ICONE = {"APROVADO": "🟢", "REVISAO": "🟡", "REJEITADO": "🔴", "PAGO": "🔵"}
SEV = {"OK": "✅", "ALERTA": "⚠️", "CRITICO": "⛔"}


def carregar() -> pd.DataFrame:
    with store.conexao() as con:
        return pd.DataFrame(store.listar(con))


st.title("🧾 Agente de Contas a Pagar")
modo = f"Claude API ({config.MODELO_EXTRACAO} / {config.MODELO_AGENTE})" if config.llm_disponivel() \
    else "offline: regras determinísticas + extração por regex"
st.caption(f"Modo: {modo}. Dados 100% fictícios.")

with st.sidebar:
    st.header("Entrada")
    if st.button("Processar novos da inbox", type="primary", width="stretch"):
        with store.conexao() as con:
            ja = {r["arquivo"] for r in store.listar(con)}
        novos = [p for p in arquivos_da_pasta() if p.name not in ja]
        with st.spinner(f"Processando {len(novos)} documento(s)..."):
            res = processar_pasta(arquivos=novos)
        st.success(f"{len(res)} processado(s)")
    enviado = st.file_uploader("Enviar NF-e (XML) / DANFE / boleto (PDF)", type=["xml", "pdf"])
    if enviado and st.button("Processar arquivo enviado", width="stretch"):
        destino = config.INBOX_DIR / enviado.name
        destino.write_bytes(enviado.getvalue())
        r = processar_documento(destino)
        st.info(f"{ICONE.get(r['status'], '')} {r['status']}: {r['justificativa']}")

df = carregar()
if df.empty:
    st.info("Nenhum documento processado ainda. Gere a demo com `python scripts/gerar_dados_ficticios.py` "
            "e clique em **Processar novos da inbox**.")
    st.stop()

# ------------------------------------------------------------------ KPIs
total = len(df)
auto = (~df["decidido_por"].fillna("").str.startswith("humano")).sum()
bloqueado = df.loc[df["status"] == "REJEITADO", "valor_total"].sum()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Documentos", total)
c2.metric("Aprovados", int((df["status"] == "APROVADO").sum()))
c3.metric("Em revisão", int((df["status"] == "REVISAO").sum()))
c4.metric("Decididos sem intervenção", f"{auto / total:.0%}")
c5.metric("Valor bloqueado", f"R$ {bloqueado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

aba_fila, aba_venc, aba_todos, aba_audit = st.tabs(["Fila de revisão", "Vencimentos", "Todos", "Auditoria"])

with aba_fila:
    fila = df[df["status"] == "REVISAO"]
    if fila.empty:
        st.success("Nenhuma pendência. 🎉")
    analista = st.text_input("Seu nome (vai para a trilha de auditoria)", value="analista")
    for _, d in fila.iterrows():
        with st.expander(f"#{d['id']} · {d['arquivo']} · {d['nome_emitente']} · R$ {d['valor_total']:.2f}",
                         expanded=True):
            st.write(d["justificativa"])
            with store.conexao() as con:
                for v in store.verificacoes_de(con, int(d["id"])):
                    st.write(f"{SEV[v['severidade']]} **{v['regra']}**: {v['mensagem']}")
            obs = st.text_input("Observação", key=f"obs{d['id']}")
            b1, b2 = st.columns(2)
            if b1.button("Aprovar", key=f"ap{d['id']}"):
                with store.conexao() as con:
                    store.atualizar_status(con, int(d["id"]), Status.APROVADO, obs or "Aprovado na revisão",
                                           f"humano:{analista}")
                st.rerun()
            if b2.button("Rejeitar", key=f"rj{d['id']}"):
                with store.conexao() as con:
                    store.atualizar_status(con, int(d["id"]), Status.REJEITADO, obs or "Rejeitado na revisão",
                                           f"humano:{analista}")
                st.rerun()

with aba_venc:
    dias = st.slider("Horizonte (dias)", 1, 60, 15)
    limite = (date.today() + timedelta(days=dias)).isoformat()
    venc = df[(df["status"] == "APROVADO") & (df["data_vencimento"] <= limite)].sort_values("data_vencimento")
    st.metric(f"A pagar em {dias} dias", f"R$ {venc['valor_total'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    st.dataframe(venc[["data_vencimento", "nome_emitente", "valor_total", "arquivo"]], hide_index=True,
                 width="stretch")

with aba_todos:
    vis = df.assign(status=df["status"].map(lambda s: f"{ICONE.get(s, '')} {s}"))
    st.dataframe(vis[["id", "status", "arquivo", "tipo", "nome_emitente", "valor_total", "data_vencimento",
                      "decidido_por", "metodo_extracao", "justificativa"]],
                 hide_index=True, width="stretch")
    escolhido = st.selectbox("Detalhar documento", df["id"].tolist())
    linha = df[df["id"] == escolhido].iloc[0]
    st.json(json.loads(linha["dados_json"]))

with aba_audit:
    with store.conexao() as con:
        audit = pd.DataFrame([dict(r) for r in con.execute("SELECT * FROM auditoria ORDER BY id DESC")])
    st.dataframe(audit, hide_index=True, width="stretch")
