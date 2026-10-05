# Como demonstrar

Roteiro para ver as duas aplicações funcionando do ponto de vista do usuário. Cada desafio leva cerca de
5 minutos.

> **Memória:** n8n + Streamlit + navegador pesam. Em máquina com pouca RAM, demonstre um desafio por vez
> (`.\demo.ps1 -Somente d1`, feche, depois `.\demo.ps1 -Somente d2`).

## Atalho

```powershell
cd "C:\Users\paulo\OneDrive\Área de Trabalho\Case-GoGroup"
.\demo.ps1 -Somente d1    # painel do agente financeiro em http://localhost:8501
.\demo.ps1 -Somente d2    # n8n em http://localhost:5678 + log em http://127.0.0.1:8765/log
```

Se o PowerShell bloquear scripts: `powershell -ExecutionPolicy Bypass -File .\demo.ps1 -Somente d1`.

---

## Desafio 1: Agente de Contas a Pagar

**Papel:** analista do financeiro que recebe notas e boletos por e-mail.

| Passo | O que fazer no painel | O que observar |
|---|---|---|
| 1 | Barra lateral → **Processar novos da inbox** | 11 documentos lidos e decididos em segundos |
| 2 | KPIs no topo | 4 aprovados, 3 em revisão, 4 rejeitados; **valor bloqueado** em R$ |
| 3 | Aba **Fila de revisão** | Cada pendência explicada: "preço 8% acima do pedido", "faturado 500, recebido 400", "PDF com confiança baixa" |
| 4 | Escreva uma observação e clique **Aprovar** em uma pendência | Ela sai da fila; o KPI "decididos sem intervenção" muda |
| 5 | Aba **Todos** | Os rejeitados: **golpe do boleto** (nome do fornecedor real, CNPJ de terceiro), **nota duplicada**, **chave adulterada**, **fornecedor fora do cadastro** |
| 6 | "Detalhar documento" | Dados extraídos da NF (itens, valores, chave) em JSON |
| 7 | Aba **Vencimentos** | O que pagar nos próximos dias, com total (a NF que vence em 2 dias aparece como prioridade) |
| 8 | Aba **Auditoria** | Toda decisão com autor (regra, agente ou `humano:<nome>`) e horário |
| 9 | Barra lateral → envie um XML da pasta `inbox/` de novo → **Processar arquivo enviado** | Rejeitado na hora por **duplicidade** |

### Conversando com o agente (MCP)

```powershell
claude mcp add contas-a-pagar -- python "C:/Users/paulo/OneDrive/Área de Trabalho/Case-GoGroup/desafio1-agente-nf/mcp_server.py"
```

No Claude Code, peça em linguagem natural:
- "O que está pendente de revisão e por quê?"
- "Aprove a pendência 4, o reajuste foi acordado por e-mail. Meu nome é Paulo."
- "Quanto tenho a pagar nos próximos 7 dias?"
- "Me mostra o histórico do fornecedor de embalagens."

### Só pelo terminal

```powershell
cd desafio1-agente-nf
python -m ap_agent processar --offline
python -m ap_agent pendencias
python -m ap_agent vencimentos --dias 7
python -m ap_agent exportar             # data/export/lancamentos.xlsx
```

---

## Desafio 2: TikTok automático com n8n

**Papel:** quem cuida das redes sociais e quer postar todo dia sem produzir vídeo à mão.

Abra <http://localhost:5678> e entre com `admin@case.local` / `CaseGoGroup2026!`.

| Passo | O que fazer | O que observar |
|---|---|---|
| 1 | Abra o workflow **TikTok · Post automático com IA** | O fluxo inteiro desenhado: gatilhos → IA/banco de roteiros → vídeo → aprovação → publicação → log |
| 2 | Clique em **Execute workflow** (gatilho "Testar agora") | Os nós acendem verdes em sequência (~30 s; o vídeo é montado no meio) |
| 3 | Clique no nó **Normalizar roteiro** | Gancho, cenas, narração, CTA e hashtags gerados |
| 4 | Clique no nó **Renderizar vídeo** e abra o `video_url` | O vídeo vertical com narração |
| 5 | Clique em **Iniciar publicação** e **Consultar status** | `publish_id` e `PUBLISH_COMPLETE` devolvidos pela API (simulador) |
| 6 | Abra <http://127.0.0.1:8765/log> | Histórico de publicações |
| 7 | Aba **Executions** do n8n | Todas as execuções, inclusive com erro |
| 8 | Workflow **TikTok · Autenticação** | Login OAuth, callback e renovação automática de token |

### Publicar conversando com o Claude (MCP)

```powershell
claude mcp add --transport http tiktok-n8n http://localhost:5678/mcp/tiktok
```

No Claude Code: *"publica um vídeo sobre golpe do boleto e depois me mostra o histórico"*.
Sem Claude Code: `python desafio2-tiktok-n8n\scripts\testar_mcp.py "planilha"`.

### Pelo formulário

No nó **Formulário (tema manual)**, copie a *Production URL*, abra no navegador, digite um tema e envie.

### Com a conta TikTok real

Depois de seguir [setup-tiktok.md](desafio2-tiktok-n8n/docs/setup-tiktok.md), troque `api_base` no
workflow de autenticação para `https://open.tiktokapis.com`. O vídeo aparece no app do TikTok da conta de
teste, como **privado** (regra do TikTok para apps ainda não auditados).

---

## Roteiro do vídeo de demonstração (3 a 5 min)

| Tempo | Cena | Fala sugerida |
|---|---|---|
| 0:00–0:20 | README raiz | "Dois desafios: um agente financeiro com IA e um fluxo n8n que publica no TikTok, ambos com MCP." |
| 0:20–0:40 | Slide/README: a dor | "O financeiro digita notas, confere pedido no olho e cai em golpe de boleto." |
| 0:40–2:00 | Painel D1, passos 1 a 5 e 9 | "Processou tudo em segundos, só 3 exceções para mim, e barrou fraude e duplicidade." |
| 2:00–2:30 | Claude Code + MCP D1 | "Também converso com o agente: o que está pendente? aprove a 4." |
| 2:30–2:50 | Plano de implantação | "Cronograma de 10 semanas, custo de ≈ US$ 27/mês de IA, payback em 1 a 3 meses, riscos mapeados." |
| 2:50–4:10 | n8n, passos 1 a 6 | "O roteiro vira vídeo com narração e é publicado pela API oficial do TikTok." |
| 4:10–4:40 | MCP no n8n | "E posso pedir o post em linguagem natural." |
| 4:40–5:00 | Diferenciais | "Aprovação humana, fallback sem IA, tratamento de erros e custo praticamente zero." |
