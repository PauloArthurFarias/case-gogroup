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
| 10 | Com o e-mail configurado (README do Desafio 1): mande para a caixa de teste um e-mail com notas anexadas e clique em **Buscar e-mails** | Os anexos chegam sozinhos à inbox e aparecem decididos; a Auditoria mostra `EMAIL_RECEBIDO` |

### Conversando com o agente (MCP)

```powershell
claude mcp add contas-a-pagar -- python "C:/Users/paulo/OneDrive/Área de Trabalho/Case-GoGroup/desafio1-agente-nf/mcp_server.py"
```

No Claude Code, peça em linguagem natural:
- "O que está pendente de revisão e por quê?"
- "Aprove a pendência 4, o reajuste foi acordado por e-mail. Meu nome é Paulo."
- "Quanto tenho a pagar nos próximos 7 dias?"
- "Me mostra o histórico do fornecedor de embalagens."
- "Busque as notas novas no e-mail e me diga o que precisa da minha atenção."

### Só pelo terminal

```powershell
cd desafio1-agente-nf
python -m ap_agent processar --offline
python -m ap_agent pendencias
python -m ap_agent vencimentos --dias 7
python -m ap_agent exportar             # data/export/lancamentos.xlsx
python -m ap_agent ler-email            # busca notas no e-mail configurado
```

### Com notas reais

```powershell
cd desafio1-agente-nf
python scripts\preparar_notas_reais.py "C:\caminho\das\suas\notas" --processar
```

Mostra a decisão de cada nota real. Detalhes no README do Desafio 1.

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
