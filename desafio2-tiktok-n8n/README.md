# Post automático no TikTok com n8n e IA

Fluxo low-code no **n8n** que cria e publica sozinho vídeos curtos no TikTok:

1. escolhe o tema: agendado, por formulário ou por pedido em linguagem natural via **MCP**;
2. a **IA** escreve o roteiro (gancho, cenas, narração, CTA e hashtags), em JSON validado por schema. A IA
   pode ser um modelo gratuito via OpenRouter ou o Claude; se falhar, um banco de roteiros assume;
3. gera o **vídeo 9:16**: narração neural pt-BR, slides com legenda, zoom e transições, H.264/AAC;
4. manda a prévia no **Telegram** e espera **Publicar** ou **Descartar** (aprovação humana);
5. publica pela **TikTok Content Posting API** oficial (Direct Post), acompanha o processamento e registra
   tudo num log. Erros caem num workflow de tratamento, com mensagem clara.

**Publicação real validada em 06/10/2026:** `PUBLISH_COMPLETE` na conta de teste do sandbox
(`publish_id v_pub_file~v2-1.7693659920302147605`), com aprovação pelo Telegram. Detalhes em
[Testes realizados](#testes-realizados).

Inspirado no vídeo de referência ("This n8n AI Agent will AUTOMATE your Social Media"). As melhorias estão
em [Diferenciais](#diferenciais).

![capa](assets/exemplo_capa.png)

Vídeo gerado pelo fluxo: [`assets/exemplo_golpe_do_boleto.mp4`](assets/exemplo_golpe_do_boleto.mp4) (27,8 s).

## Arquitetura

```mermaid
flowchart LR
    subgraph Gatilhos
      A1[Agendado 11h]
      A2[Formulário]
      A3[MCP: criar_post_tiktok<br/>Claude Code/Desktop]
      A4[Testar agora]
    end
    A1 & A2 & A3 & A4 --> C[Config]
    C --> D{usar_ia?}
    D -- sim --> P{provedor}
    P -- openrouter --> E1[OpenRouter<br/>modelo gratuito]
    P -- anthropic --> E2[Claude API]
    D -- não --> F[Banco de roteiros]
    E1 & E2 -- erro/limite --> F
    E1 & E2 --> G[Normalizar roteiro]
    F --> G
    G --> H[Serviço de mídia<br/>TTS + slides + ffmpeg]
    H --> I{exigir_aprovacao?}
    I -- sim --> J[Telegram: prévia<br/>+ Publicar/Descartar]
    J -- Publicar --> K
    I -- não --> K[Subworkflow: token válido<br/>OAuth + refresh]
    K --> L[creator_info/query]
    L --> M[video/init FILE_UPLOAD<br/>+ conferir resposta]
    M --> N[PUT upload_url]
    N --> O[Wait 5s → status/fetch<br/>loop até PUBLISH_COMPLETE]
    O --> R[Log + resultado]
    M & O -- recusa/FAILED --> X[Erro claro → workflow de erros]
```

### Workflows (`workflows/`)

| Arquivo | O que faz |
|---|---|
| `01_tiktok_post_automatico.json` | Fluxo principal (34 nós): gatilhos, roteiro (IA ou banco), vídeo, aprovação, publicação, log |
| `02_tiktok_autenticacao.json` | OAuth do TikTok: `GET /webhook/tiktok/login` (redireciona), `GET /webhook/tiktok/callback` (troca `code` por token, valida `state`) e subworkflow que entrega um `access_token` válido, renovando com `refresh_token` |
| `03_tiktok_erros.json` | *Error Trigger*: registra a falha, o nó e o link da execução |
| `04_tiktok_mcp_server.json` | **Servidor MCP** em `/mcp/tiktok` com `criar_post_tiktok(tema)` e `historico_publicacoes()` |

Os JSONs são gerados por `workflows/src/build.py` (fluxo como código). Os do repositório são **genéricos e sem
segredos**. A configuração local (ids de credenciais, app TikTok, Telegram) fica em `workflows/src/local.json`,
fora do git, e é aplicada por `scripts/configurar.py`.

### Serviço de mídia (`media_service/`)

Pequeno serviço HTTP local (Python stdlib) que o n8n chama via *HTTP Request*:

| Rota | Função |
|---|---|
| `POST /render` | Roteiro → `video.mp4` 1080×1920 + capa. Narração com **edge-tts** (voz neural pt-BR gratuita), slides com Pillow, montagem com ffmpeg |
| `GET/POST /tokens` | Guarda os tokens OAuth em arquivo local fora do git |
| `GET/POST /log` | Histórico de publicações (CSV) |
| `/mock-tiktok/...` | **Simulador da Content Posting API**: mesmos endpoints e contratos, inclusive a regra de conta privada (`MOCK_CONTA_PRIVADA=0` reproduz a recusa) |

Por que um serviço em vez do nó *Execute Command*: o n8n 2.x bloqueia esse nó por padrão. Com HTTP, o mesmo
desenho funciona com n8n em Docker ou na nuvem.

## Como rodar

Pré-requisitos: Python 3.10+, ffmpeg no PATH e **Node 24** (exigido pelo n8n 2.x), que pode ser portátil:

```powershell
# Node 24 portátil + n8n local (uma vez)
# baixe https://nodejs.org/dist/latest-v24.x/node-v24.*-win-x64.zip e extraia em $HOME\tools\node24
$env:PATH = "$HOME\tools\node24;$env:PATH"
mkdir $HOME\tools\n8n; cd $HOME\tools\n8n; npm init -y; npm install n8n

cd <repo>\desafio2-tiktok-n8n
pip install -r requirements.txt
.\importar.ps1          # importa os 4 workflows (n8n parado)
.\iniciar.ps1           # sobe serviço de mídia (porta 8765) + n8n (porta 5678)
```

No n8n (<http://localhost:5678>), clique em **Publish** nos 4 workflows.

### Modo simulador (sem nenhuma conta)
1. Conecte a conta simulada abrindo
   `http://localhost:5678/webhook/tiktok/callback?code=teste&state=case-gogroup-csrf`.
2. Publique pelo botão *Execute workflow*, pelo formulário ou com `python scripts/testar_mcp.py "tema"`.

Sem credenciais, o roteiro vem do banco e não há aprovação. O fluxo publica no simulador.

### Modo completo (TikTok real, IA e Telegram)
Copie `.env.example` para `.env`, preencha as chaves e siga [docs/setup-tiktok.md](docs/setup-tiktok.md):
app no sandbox do TikTok, conta de teste **privada**, bot do Telegram e túnel HTTPS para o login. Depois:

```powershell
python scripts\configurar.py      # cria credenciais no n8n e aplica a configuração (sem imprimir segredos)
```

### Painel de controle (nó **Config**)

| Campo | Padrão | Efeito |
|---|---|---|
| `usar_ia` | `true` | Gera o roteiro com IA; sem credencial ou com falha, usa o banco de roteiros |
| `provedor_ia` | `openrouter` | `openrouter` (modelo gratuito) ou `anthropic` (Claude, exige credencial Anthropic) |
| `modelo_openrouter` | `nvidia/nemotron-3-super-120b-a12b:free` | Modelo gratuito usado no OpenRouter |
| `exigir_aprovacao` | `false` (ligado pelo `configurar.py` quando há bot) | Envia a prévia ao Telegram e espera a decisão |
| `privacidade_preferida` | `SELF_ONLY` | Usada se estiver entre as opções retornadas por `creator_info` |
| `marca` | `@automacao.na.pratica` | Handle exibido no vídeo |

A troca **simulador ↔ API real** é um campo: `TIKTOK_MODO` no `.env` (vira `api_base` no workflow de
autenticação).

## Integração MCP

Com o workflow `TikTok · Servidor MCP` publicado, qualquer cliente MCP cria posts em linguagem natural:

```bash
claude mcp add --transport http tiktok-n8n http://localhost:5678/mcp/tiktok
# no Claude Code: "publica um vídeo sobre golpe do boleto e me mostra o histórico"
```

Com a aprovação ligada, a ferramenta responde que o fluxo está esperando a decisão humana, e o post segue
sozinho quando alguém toca em **Publicar** no Telegram.

## Testes realizados

Ambiente: n8n 2.41.7 local, Node 24.21.

| Cenário | Modo | Resultado |
|---|---|---|
| **Post real com aprovação** | TikTok real (sandbox) + Telegram | Prévia no Telegram → **Publicar** → `PUBLISH_COMPLETE`, `modo: api-real`, `SELF_ONLY`, vídeo no perfil da conta de teste |
| Conta de teste pública | TikTok real | API recusou com `unaudited_client_can_only_post_to_private_accounts`; após deixar a conta privada, publicou. O fluxo agora traduz esse erro em instrução |
| OAuth real | TikTok real + túnel | Login → autorização → token (24 h) e refresh token (365 dias), escopos `user.info.basic,video.publish` |
| Ponta a ponta via MCP | Simulador | `PUBLISH_COMPLETE`, 845.748 bytes enviados por PUT e conferidos |
| OAuth: `state` inválido | Simulador | HTTP 400 "Callback inválido" (proteção CSRF) |
| Renovação de token | Simulador | Token vencido renovado pelo refresh token; post concluído |
| Conta desconectada | Simulador | Erro claro; workflow de erros registrou nó, mensagem e link |
| IA indisponível | OpenRouter (limite diário gratuito atingido, erro 429) | Banco de roteiros assumiu; post publicado mesmo assim |
| IA sem credencial | Claude | Nó falhou e caiu no banco; post publicado |

Log de exemplo: [`assets/exemplo_log_publicacoes.csv`](assets/exemplo_log_publicacoes.csv).

## Diferenciais

| Vídeo de referência | Este fluxo |
|---|---|
| Publica direto | Aprovação humana pelo Telegram (*send-and-wait*), testada com post real |
| Depende 100% da IA | *Fallback* para banco de roteiros se a IA falhar, recusar ou atingir limite |
| IA paga | Modelo gratuito via OpenRouter; Claude como opção |
| Saída de IA em texto livre | *Structured output* com JSON Schema: sem parsing frágil |
| Ferramentas pagas de vídeo | Vídeo montado localmente, custo zero (TTS neural gratuito + ffmpeg) |
| — | Respeita as regras da API: `creator_info` antes de postar, `is_aigc=true`, polling de status |
| — | OAuth completo com `state` anti-CSRF e renovação automática do token |
| — | Erros traduzidos em ação (ex.: "deixe a conta privada"), workflow de erros e log |
| — | Servidor MCP: publicar conversando com o Claude |
| — | Simulador da API para testar sem conta; segredos fora do git |

## Custos

| Item | Custo |
|---|---|
| n8n self-hosted, edge-tts, ffmpeg, TikTok API, Telegram, túnel Cloudflare | R$ 0 |
| Roteiro por IA no OpenRouter (modelo gratuito) | R$ 0 (limite de 50 chamadas/dia sem créditos) |
| Opcional: Claude no lugar do modelo gratuito | ≈ US$ 0,03 por vídeo; 30 vídeos/mês ≈ US$ 1 |
| Opcional: servidor para rodar 24 h | US$ 0–10/mês |

## Limitações

- **App sem auditoria (sandbox):** só publica em conta **privada**, e os vídeos ficam visíveis só para o dono.
  Posts públicos exigem a auditoria do app pelo TikTok.
- **Modelo gratuito:** 50 chamadas/dia no OpenRouter sem créditos; acima disso, o banco de roteiros assume.
- **Túnel rápido:** a URL muda a cada execução do cloudflared. Só é preciso no login e para aprovar pelo
  celular; para uso contínuo, um túnel nomeado ou domínio fixo.
- **Rate limit da API do TikTok:** 6 requisições/min por token. O fluxo faz 1 post por execução.
- **Vídeos < 64 MB:** upload em 1 chunk (os gerados têm cerca de 1 MB).
- **Fora do n8n:** tokens e log ficam no serviço local. Em produção, usar n8n Credentials/Data Tables ou
  banco de dados.
