# Como demonstrar

Roteiro para ver as duas aplicações funcionando do ponto de vista do usuário. O Desafio 1 leva cerca de
15 minutos; o Desafio 2, cerca de 10.

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

**Antes de começar:** o `.env` de `desafio1-agente-nf` precisa ter a chave de IA e a caixa de e-mail
(veja o README do Desafio 1). Sem eles, tudo funciona em modo offline: a DANFE vai para revisão e o botão de
e-mail fica desabilitado.

| Passo | O que fazer | O que observar |
|---|---|---|
| 1 | `.\demo.ps1 -Somente d1` | Recria os 11 documentos fictícios, zera a base e abre o painel. O topo mostra o modelo de IA em uso |
| 2 | Recorte `nfe_010_paletes_vence_em_2_dias.xml` e `boleto_009_fraude_beneficiario.pdf` de `desafio1-agente-nf\inbox` para a Área de Trabalho | Esses dois vão chegar por e-mail no passo 6 |
| 3 | Barra lateral → **Processar novos da inbox** | 9 documentos decididos (cerca de 1 min com IA): 4 aprovados, 2 em revisão, 3 rejeitados |
| 4 | Aba **Fila de revisão** | Preço 8% acima do pedido e 100 luvas cobradas sem entrega, cada uma com justificativa e ação sugerida escritas pelo agente |
| 5 | Escreva seu nome e uma observação, clique **Aprovar** numa pendência; depois aba **Auditoria** | A decisão humana fica registrada com autor e horário |
| 6 | Do seu e-mail pessoal, envie os 2 arquivos do passo 2 para a caixa de teste; no painel, **Buscar e-mails** | A NF dos paletes é aprovada com **PRIORIDADE** (vence em 2 dias) e o boleto é **REJEITADO por golpe** (nome do fornecedor real, CNPJ de terceiro). A Auditoria mostra `EMAIL_RECEBIDO` |
| 7 | Aba **Todos** → "Detalhar documento" na DANFE | Os dados que a IA leu do PDF; os rejeitados com o motivo (duplicidade, chave adulterada, fornecedor fora do cadastro, golpe) |
| 8 | Aba **Vencimentos** | O que pagar nos próximos dias, com total |
| 9 | Barra lateral → envie de novo um XML já processado → **Processar arquivo enviado** | Rejeitado na hora por **duplicidade** |

Resultado final esperado com IA: **5 aprovados, 2 em revisão, 4 rejeitados**. Sem IA: 4, 3 e 4, porque a
DANFE em PDF vai para revisão.

**Se algo der errado:**
- **IA lenta ou erro 429 no log:** limite do modelo gratuito. Os documentos são decididos pelas regras e a
  demonstração continua; espere alguns minutos para repetir.
- **"Buscar e-mails" não encontra nada:** confira se o e-mail chegou como **não lido** na caixa de teste.
- **Recomeçar do zero:** rode `.\demo.ps1 -Somente d1` de novo. O script fecha o painel anterior.

### Conversando com o agente (MCP)

```powershell
claude mcp add contas-a-pagar -- python "C:/Users/paulo/OneDrive/Área de Trabalho/Case-GoGroup/desafio1-agente-nf/mcp_server.py"
```

Abra um terminal na pasta do case, rode `claude` e confira com `/mcp` que `contas-a-pagar` está conectado.
O MCP usa a mesma base do painel: atualize o painel (F5) para ver as decisões feitas pelo chat.

No Claude Code, peça em linguagem natural:
- "O que está pendente de revisão e por quê?"
- "Aprove a pendência das luvas: o restante foi entregue hoje. Meu nome é Paulo."
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

**Antes de começar:** `.\demo.ps1 -Somente d2` sobe o serviço de vídeo e o n8n. Abra <http://localhost:5678>
e entre com `admin@case.local` / `CaseGoGroup2026!`.

A instância local está configurada no **modo completo**: TikTok real (conta de teste privada), roteiro por IA
gratuita (OpenRouter, com Gemini de reserva), vídeo com fotos do Pixabay, legendas dinâmicas e trilha, e
aprovação pelo Telegram. Cada publicação vai de verdade para a conta de teste, como vídeo privado.
Para demonstrar sem conta nenhuma, veja "Modo simulador" no README do Desafio 2.

| Passo | O que fazer | O que observar |
|---|---|---|
| 1 | Abra o workflow **TikTok · Post automático com IA** | O fluxo desenhado: gatilhos → IA (OpenRouter ou Claude) / banco de roteiros → vídeo → aprovação → publicação → log |
| 2 | Clique em **Execute workflow** (gatilho "Testar agora") | Os nós acendem em sequência; o fluxo **pausa** em "Telegram: aprovar?" |
| 3 | No Telegram, abra a conversa com o seu bot | Chegam o vídeo (fotos, emojis, legendas palavra a palavra, trilha) e a pergunta com os botões **Publicar** / **Descartar** |
| 4 | Toque em **Publicar** (use o Telegram no próprio computador, Web ou Desktop, ou veja a nota abaixo) | O n8n retoma: token, envio ao TikTok, consulta de status até `PUBLISH_COMPLETE` |
| 5 | Abra o TikTok com a conta de teste → Perfil | O vídeo publicado, com cadeado (privado) |
| 6 | No n8n, clique nos nós **Normalizar roteiro**, **Renderizar vídeo** e **Consultar status** | Roteiro gerado, com a origem (`ia:` + modelo usado, ou `banco`); link do vídeo, quantas cenas tiveram foto; `publish_id` e status |
| 7 | Abra <http://127.0.0.1:8765/log> | Histórico com `modo: api-real` |
| 8 | Repita o passo 2 e toque em **Descartar** | Nada é publicado; o log registra `DESCARTADO` |
| 9 | Aba **Executions** e workflow **TikTok · Autenticação** | Todas as execuções; login OAuth, callback e renovação automática do token |

**Botões do Telegram:** eles abrem um link do n8n. A cada início, o `iniciar.ps1` (chamado pelo `demo.ps1`)
abre um túnel HTTPS novo e usa o endereço dele nesses links, então a aprovação funciona no computador e no
celular. O endereço aparece em verde na janela do n8n; fechar essa janela fecha o túnel. Se o túnel não abrir
(sem internet), aparece um aviso e os links passam a ser `localhost`, que funcionam só no computador.
Mensagens de uma sessão anterior apontam para o túnel antigo: nelas, troque o começo do link por
`http://localhost:5678`.

**Se algo der errado:** a mensagem de erro do fluxo diz o motivo e o que fazer. Por exemplo, "conta precisa
ser privada" ou "refaça o login". A tabela completa está em `desafio2-tiktok-n8n/docs/setup-tiktok.md`.

### Publicar conversando com o Claude (MCP)

```powershell
claude mcp add --transport http tiktok-n8n http://localhost:5678/mcp/tiktok
```

No Claude Code: *"publica um vídeo sobre golpe do boleto e depois me mostra o histórico"*. Com a aprovação
ligada, o Claude avisa que o post aguarda a decisão no Telegram.
Sem Claude Code: `python desafio2-tiktok-n8n\scripts\testar_mcp.py "planilha"`.

### Pelo formulário

No nó **Formulário (tema manual)**, copie a *Production URL*, abra no navegador, digite um tema e envie.

---
