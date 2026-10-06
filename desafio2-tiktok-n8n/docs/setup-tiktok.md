# Publicar de verdade no TikTok (sandbox, gratuito)

Este é o passo a passo usado para o primeiro post real, feito em 06/10/2026 (`PUBLISH_COMPLETE`,
`publish_id v_pub_file~v2-1.7693659920302147605`). São cerca de 30 minutos de configuração, uma vez só.

> **O que esperar:** enquanto o app não passar pela auditoria do TikTok, ele só publica em **conta privada**,
> e os vídeos ficam visíveis apenas para o dono. É a regra oficial para apps em sandbox, e é o que o case
> pede ("crie usuários de teste").

## 1. Conta de teste
Crie no app do TikTok uma conta nova só para o projeto e deixe-a **privada**: Perfil → ☰ →
**Configurações e privacidade → Privacidade → Conta privada**.

Sem isso, a API recusa a publicação com `unaudited_client_can_only_post_to_private_accounts`. O fluxo mostra
essa mensagem com a instrução de correção.

## 2. Textos legais públicos
O formulário do app exige links de Termos de Uso e Política de Privacidade. Os textos estão prontos em
[`docs/app-tiktok/`](app-tiktok/). Publique cada um como **gist público** em <https://gist.github.com> e
guarde os links.

## 3. Criar o app e configurar o **Sandbox**
Em <https://developers.tiktok.com>, vá em **Manage apps → Connect an app**. No topo da página do app, selecione
**Sandbox** (crie um). A configuração de Production fica em branco: só é usada para auditoria.

No Sandbox, preencha e salve:

| Seção | Valor |
|---|---|
| App icon | [`docs/app-tiktok/icone-1024.png`](app-tiktok/icone-1024.png) |
| App name / Category / Description | "Automação na Prática - Case" / Education / descrição curta do projeto |
| Terms of Service URL / Privacy Policy URL | links dos gists |
| Platforms | **Web**; Website URL = link do gist dos termos |
| Products | **Login Kit** e **Content Posting API** (com **Direct Post** ativado) |
| Scopes | `user.info.basic` e `video.publish` |
| Login Kit → Redirect URI (Web) | `https://<túnel>/webhook/tiktok/callback` (passo 5) |
| Sandbox settings → Target users | a conta de teste |

Copie o **Client key** (do sandbox começa com `sb`) e o **Client secret** para `desafio2-tiktok-n8n/.env`
(modelo em `.env.example`).

## 4. Bot do Telegram (aprovação humana, opcional)
No Telegram, converse com **@BotFather**, envie `/newbot` e copie o token para `TELEGRAM_BOT_TOKEN` no
`.env`. Depois mande `/start` para o seu bot: é assim que o script descobre o seu chat.

## 5. Túnel HTTPS, só para o login
O TikTok exige Redirect URI em HTTPS. Com o n8n rodando:

```powershell
$HOME\tools\cloudflared.exe tunnel --url http://localhost:5678
```

Copie a URL `https://....trycloudflare.com` e:
1. cadastre `https://....trycloudflare.com/webhook/tiktok/callback` como Redirect URI no Sandbox (passo 3);
2. no `.env`, preencha `TIKTOK_REDIRECT_URI` com a mesma URL e `TIKTOK_MODO=real`;
3. para os botões do Telegram funcionarem no celular, reinicie o n8n com
   `$env:N8N_WEBHOOK_URL = "https://....trycloudflare.com/"` antes de `.\iniciar.ps1`.

Depois do login, o túnel só é necessário para a aprovação pelo celular. A publicação é feita do n8n para o
TikTok, sem túnel. O token de acesso dura 24 h e se renova sozinho pelo refresh token, que vale 365 dias.

## 5b. Chaves gratuitas opcionais
- **Gemini** (reserva de IA): <https://aistudio.google.com/apikey> → **Create API key** → `GEMINI_API_KEY` no `.env`.
- **Pixabay** (fotos de fundo): crie a conta e copie a chave em <https://pixabay.com/api/docs/> →
  `PIXABAY_API_KEY` no `.env`. O Pexels (`PEXELS_API_KEY`) também funciona, se estiver emitindo chaves.

## 6. Aplicar a configuração
```powershell
cd desafio2-tiktok-n8n
python scripts\configurar.py
```
O script:
- cria no n8n as credenciais **OpenRouter**, **Gemini** e **Telegram**;
- escolhe o modelo Gemini pela latência medida e valida a chave de fotos;
- encontra o seu chat do Telegram;
- grava `workflows/src/local.json`, que fica fora do git;
- gera, importa e ativa os workflows com essa configuração.

Nenhum segredo é impresso.

## 7. Conectar a conta e publicar
1. No navegador, entre no tiktok.com com a conta de teste e abra `https://<túnel>/webhook/tiktok/login`.
   Clique em **Autorizar**: aparece "Conta TikTok conectada".
2. Publique pelo botão do n8n, pelo formulário ou pelo Claude (MCP). Com a aprovação ligada, a prévia chega no
   Telegram. Toque em **Publicar**.
3. O vídeo aparece no perfil da conta de teste, com cadeado (privado). O log em
   `http://127.0.0.1:8765/log` registra `modo: api-real` e o `publish_id`.

## Erros comuns

| Mensagem | Causa | Solução |
|---|---|---|
| `unaudited_client_can_only_post_to_private_accounts` | Conta de teste pública | Deixar a conta privada (passo 1) |
| Tela do TikTok com erro de `redirect_uri` | URL cadastrada diferente da usada | Copiar exatamente a URL do túnel + `/webhook/tiktok/callback` |
| Erro de `client_key` | Chave de Production no lugar da do Sandbox | Usar as chaves do Sandbox |
| Conta não pode autorizar o app | Target user ainda não ativo | Aguardar até 1 h após adicionar |
| "Conta TikTok não conectada" | Tokens ausentes ou revogados | Refazer o login (passo 7.1) |
| Botões do Telegram abrem `localhost` no celular | n8n sem `N8N_WEBHOOK_URL` público | Reiniciar o n8n com a URL do túnel (passo 5.3) |

## Referências
- Content Posting API (Direct Post): <https://developers.tiktok.com/doc/content-posting-api-reference-direct-post>
- Upload de mídia: <https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide>
- Sandbox: <https://developers.tiktok.com/doc/add-a-sandbox>
- Login Kit (Web): <https://developers.tiktok.com/doc/login-kit-web>
