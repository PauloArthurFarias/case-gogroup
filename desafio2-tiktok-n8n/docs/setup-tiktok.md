# Configurando o app no TikTok for Developers

Passo a passo para publicar de verdade (sair do modo simulador). Leva cerca de 20 minutos, mais o tempo
de análise do TikTok, que pode levar dias. Por isso este é o **primeiro passo** do cronograma.

## 1. Criar o app

1. Acesse <https://developers.tiktok.com/> e entre com uma conta TikTok. Use uma **conta de teste**
   criada para o case, não uma pessoal.
2. **Manage apps → Connect an app.** Tipo: *Web*. Preencha nome, ícone, categoria, descrição, URLs de
   termos de uso e política de privacidade. Podem ser páginas simples hospedadas no GitHub Pages.
3. Em **Products**, adicione:
   - **Login Kit**
   - **Content Posting API**: habilite **Direct Post**.
4. Em **Scopes**, marque `user.info.basic` e `video.publish`.
5. Em **Login Kit → Redirect URI**, cadastre a URL HTTPS do túnel (passo 3), por exemplo
   `https://SEU-TUNEL.trycloudflare.com/webhook/tiktok/callback`.

## 2. Sandbox e usuário de teste

1. No topo do app, troque para **Sandbox** e crie um sandbox.
2. Em **Sandbox settings → Target users**, adicione a conta TikTok de teste.
3. Copie **Client key** e **Client secret** do sandbox.

> **Limitação oficial:** enquanto o app não passar pela auditoria (*audit*) do TikTok, todo conteúdo
> publicado via Direct Post fica **privado** (`SELF_ONLY`), visível só para o dono da conta. É o
> comportamento esperado para a demo. Para posts públicos, é preciso submeter o app à auditoria depois
> de gravar o vídeo de demonstração do fluxo.

## 3. Túnel HTTPS para o n8n local

O TikTok só aceita *redirect URI* HTTPS. Com o n8n rodando em `localhost:5678`:

```powershell
# baixe cloudflared.exe (https://github.com/cloudflare/cloudflared/releases) e rode:
cloudflared tunnel --url http://localhost:5678
```

Copie a URL `https://....trycloudflare.com` e reinicie o n8n com ela:

```powershell
$env:N8N_WEBHOOK_URL = "https://....trycloudflare.com/"
.\iniciar.ps1
```

O túnel rápido do cloudflared muda de URL a cada execução. Atualize a *Redirect URI* no TikTok quando
ela mudar, ou use um túnel nomeado ou um ngrok com domínio fixo.

## 4. Conectar a conta (OAuth)

1. No n8n, abra o nó **Config** do workflow `TikTok · OAuth` e preencha `client_key`,
   `client_secret` e `redirect_uri`. Ative o workflow.
2. Abra no navegador a URL de autorização. O workflow a mostra em `GET /webhook/tiktok/login`:
   `https://SEU-TUNEL/webhook/tiktok/login`.
3. Autorize com a conta de teste. O callback troca o `code` pelo `access_token`/`refresh_token` e os
   guarda no serviço de mídia (`tokens.json`, fora do git).
4. O `access_token` dura 24 h. O subworkflow `TikTok · Token válido` renova sozinho usando o
   `refresh_token`, que dura 365 dias.

## 5. Virar a chave do simulador para a API real

No nó **Config** do workflow principal:

| Campo | Simulador | Real |
|---|---|---|
| `tiktok_api` | `http://127.0.0.1:8765/mock-tiktok` | `https://open.tiktokapis.com` |

Nada mais muda: o simulador implementa os mesmos endpoints e contratos
(`creator_info/query`, `video/init`, `PUT upload_url` com `Content-Range`, `status/fetch`).

## Referências

- Content Posting API (Direct Post): <https://developers.tiktok.com/doc/content-posting-api-reference-direct-post>
- Upload de mídia: <https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide>
- OAuth v2: <https://developers.tiktok.com/doc/oauth-user-access-token-management>
- Diretrizes de UX exigidas na auditoria: <https://developers.tiktok.com/doc/content-sharing-guidelines>
