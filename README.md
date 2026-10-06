# Case GoGroup: Estágio de RPA

Entrega dos dois desafios do Business Case, construída com **Claude Code**.

| | Desafio 1: Agente de IA | Desafio 2: TikTok automático |
|---|---|---|
| **O quê** | Agente de Contas a Pagar: lê NF-e/DANFE/boletos, faz o 3-way match, barra fraude e duplicidade, entrega só as exceções ao analista | Fluxo n8n que cria roteiro com IA, monta o vídeo 9:16 com narração e publica pela API oficial do TikTok |
| **Stack** | Python, IA (Claude ou modelo gratuito via OpenRouter), e-mail IMAP, SQLite, Streamlit, **servidor MCP** | **n8n 2.41**, IA gratuita (OpenRouter → Gemini) ou Claude, edge-tts, ffmpeg, Pixabay, TikTok Content Posting API, Telegram, **servidor MCP no n8n** |
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
| Publicação automática | TikTok Content Posting API (Direct Post) com OAuth e renovação de token. **Validada com post real** na conta de teste do sandbox |
| Usuários de teste | Sandbox + conta de teste (privada) no TikTok for Developers, usada no post real ([setup](desafio2-tiktok-n8n/docs/setup-tiktok.md)); simulador da API para testes locais |
| Inovar / melhorias | Aprovação humana pelo Telegram, IA gratuita em cadeia (OpenRouter → Gemini → banco de roteiros), vídeo com fotos, legendas dinâmicas e trilha própria, *structured output*, vídeo a custo zero, erros traduzidos em ação, simulador ([diferenciais](desafio2-tiktok-n8n/README.md#diferenciais)) |
| **Se possível, integração com MCP** | **Duas:** servidor MCP do agente financeiro (Python, 8 ferramentas) e servidor MCP no n8n (`criar_post_tiktok`) |
| Ferramentas pagas só com aprovação | Nada pago foi usado: a demo do D1 roda com modelo gratuito (OpenRouter). Em produção, a recomendação é a Claude API (≈ US$ 27/mês no D1, ≈ US$ 1/mês no D2), sujeita a aprovação |

## Como foi validado

- **Desafio 1:** 18 testes automatizados (`pytest`), incluindo ponta a ponta com 11 documentos fictícios
  (todos com o status esperado), o guard-rail da IA e o loop do agente com cliente simulado. Servidor MCP
  testado com cliente MCP real. Painel Streamlit testado headless. Validado com IA real (OpenRouter e,
  como reserva, Gemini) e com e-mail real.
- **Desafio 2:** executado no n8n 2.41.7 local. **4 posts reais** no TikTok (sandbox, conta de teste privada),
  disparados pelo n8n e pelo servidor MCP e aprovados pelo Telegram, até `PUBLISH_COMPLETE`; o último com
  roteiro escrito pelo Gemini (reserva) e o visual completo (fotos, emojis, legendas palavra a palavra, trilha). OAuth real,
  renovação de token, conta desconectada, recusa da API e falha da IA (fallback) também testados.
  Detalhes em [Testes realizados](desafio2-tiktok-n8n/README.md#testes-realizados).

### O que depende de credenciais externas

| Item | Precisa de | Status |
|---|---|---|
| Extração de PDF e agente investigador com IA (D1) | Chave de IA no `.env` (OpenRouter gratuito ou Claude) | **Validado com modelo real** (OpenRouter): demo 5/2/4, DANFE lida pela IA, exceções investigadas |
| Leitura de notas por e-mail (D1) | Gmail com senha de app no `.env` | **Validado com caixa real**: anexos baixados, processados e auditados |
| Roteiro gerado por IA (D2) | Chaves OpenRouter e Gemini (gratuitas) | **Validado em post real**: com o OpenRouter sem cota, o Gemini escreveu o roteiro |
| Publicação na conta real do TikTok (D2) | App sandbox + conta de teste privada | **Validada**: `PUBLISH_COMPLETE` em 06/10/2026, com aprovação pelo Telegram |

## Estrutura

```
Case-GoGroup/
├── Estágio de RPA.pdf                 # enunciado
├── desafio1-agente-nf/                # agente de contas a pagar (Python + MCP + Streamlit)
└── desafio2-tiktok-n8n/               # workflows n8n + serviço de mídia + simulador TikTok
```
