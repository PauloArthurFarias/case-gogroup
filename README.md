# Case GoGroup: Estágio de RPA

Entrega dos dois desafios do Business Case, construída com **Claude Code**.

| | Desafio 1: Agente de IA | Desafio 2: TikTok automático |
|---|---|---|
| **O quê** | Agente de Contas a Pagar: lê NF-e/DANFE/boletos, faz o 3-way match, barra fraude e duplicidade, entrega só as exceções ao analista | Fluxo n8n que cria roteiro com IA, monta o vídeo 9:16 com narração e publica pela API oficial do TikTok |
| **Stack** | Python, IA (Claude ou modelo gratuito via OpenRouter), e-mail IMAP, SQLite, Streamlit, **servidor MCP** | **n8n 2.41**, Claude API, edge-tts, ffmpeg, TikTok Content Posting API, **servidor MCP no n8n** |
| **Pasta** | [`desafio1-agente-nf/`](desafio1-agente-nf/) | [`desafio2-tiktok-n8n/`](desafio2-tiktok-n8n/) |
| **Comece por** | [README](desafio1-agente-nf/README.md) · [Plano de implantação](desafio1-agente-nf/docs/plano-implantacao.md) | [README](desafio2-tiktok-n8n/README.md) · [Setup do TikTok](desafio2-tiktok-n8n/docs/setup-tiktok.md) |

**Ver funcionando:** `.\demo.ps1 -Somente d1` ou `-Somente d2` e siga o
[roteiro de demonstração](COMO_DEMONSTRAR.md).

## O que o case pede → onde está

| Requisito do documento | Entrega |
|---|---|
| Agente de IA/automação criado com ferramenta de apoio (Claude Code, Cursor...) | Todo o código foi desenvolvido com Claude Code; o agente usa IA (Claude ou modelo gratuito via OpenRouter, validado com modelo real) |
| Otimizar processo de uma área de negócio | Financeiro / Contas a Pagar |
| Dor real, ganho de tempo/eficiência/inteligência | Digitação e conferência manual de NF, duplicidade, golpe do boleto, multas por atraso ([README D1](desafio1-agente-nf/README.md#a-dor)) |
| Documentação completa da automação | [README](desafio1-agente-nf/README.md) + [arquitetura, regras, modelo de dados, runbook](desafio1-agente-nf/docs/arquitetura.md) |
| Plano de ação para produção: cronograma de integrações | [Plano §2](desafio1-agente-nf/docs/plano-implantacao.md#2-cronograma-10-semanas) |
| Planejamento de custos | [Plano §4](desafio1-agente-nf/docs/plano-implantacao.md#4-custos) (API, infra, implantação, ROI/payback) |
| Antecipação de problemas e desafios | [Plano §5](desafio1-agente-nf/docs/plano-implantacao.md#5-riscos-e-mitigação) (9 riscos com mitigação) + KPIs e governança |
| Postagem automática no TikTok com low-code, de preferência n8n | 4 workflows n8n ([README D2](desafio2-tiktok-n8n/README.md)) |
| Publicação automática | TikTok Content Posting API (Direct Post) com OAuth e renovação de token |
| Usuários de teste | Sandbox + conta de teste no TikTok for Developers ([setup](desafio2-tiktok-n8n/docs/setup-tiktok.md)); simulador da API para testes locais |
| Inovar / melhorias | Aprovação humana, *fallback* sem IA, *structured output*, vídeo a custo zero, workflow de erros, simulador ([diferenciais](desafio2-tiktok-n8n/README.md#diferenciais)) |
| **Se possível, integração com MCP** | **Duas:** servidor MCP do agente financeiro (Python, 8 ferramentas) e servidor MCP no n8n (`criar_post_tiktok`) |
| Ferramentas pagas só com aprovação | Nada pago foi usado: a demo do D1 roda com modelo gratuito (OpenRouter). Em produção, a recomendação é a Claude API (≈ US$ 27/mês no D1, ≈ US$ 1/mês no D2), sujeita a aprovação |

## Como foi validado

- **Desafio 1:** 16 testes automatizados (`pytest`), incluindo ponta a ponta com 11 documentos fictícios
  (todos com o status esperado), o guard-rail da IA e o loop do agente com cliente simulado. Servidor MCP
  testado com cliente MCP real. Painel Streamlit testado headless.
- **Desafio 2:** executado no n8n 2.41.7 local. Post ponta a ponta disparado **pelo servidor MCP do n8n**
  até `PUBLISH_COMPLETE` no simulador da API. OAuth (login, callback, state inválido), renovação de token,
  conta desconectada (workflow de erros) e falha da IA (fallback) também testados.
  Detalhes em [Testes realizados](desafio2-tiktok-n8n/README.md#testes-realizados).

### O que depende de credenciais externas

| Item | Precisa de | Status |
|---|---|---|
| Extração de PDF e agente investigador com IA (D1) | Chave de IA no `.env` (OpenRouter gratuito ou Claude) | **Validado com modelo real** (OpenRouter): demo 5/2/4, DANFE lida pela IA, exceções investigadas |
| Leitura de notas por e-mail (D1) | Gmail com senha de app no `.env` | **Validado com caixa real**: anexos baixados, processados e auditados |
| Roteiro gerado por IA (D2) | Credencial Anthropic no n8n | Nó pronto; *fallback* testado |
| Publicação na conta real do TikTok (D2) | App aprovado no TikTok for Developers + túnel HTTPS | Passo a passo em [setup-tiktok.md](desafio2-tiktok-n8n/docs/setup-tiktok.md); troca simulador→real é um campo |

## Estrutura

```
Case-GoGroup/
├── Estágio de RPA.pdf                 # enunciado
├── desafio1-agente-nf/                # agente de contas a pagar (Python + MCP + Streamlit)
└── desafio2-tiktok-n8n/               # workflows n8n + serviço de mídia + simulador TikTok
```
