"""Gera os workflows n8n (JSON importável) a partir de uma descrição em Python.

Manter os fluxos como código facilita revisão em PR e evita editar JSON gigante à mão.
Uso:
  python workflows/src/build.py          -> workflows/*.json (genéricos, sem segredos: vão para o git)
  python workflows/src/build.py --local  -> workflows/local/*.json, aplicando workflows/src/local.json
                                            (ids de credenciais, app TikTok, Telegram; fora do git)
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parent
LOCAL_MODE = "--local" in sys.argv
OUT = SRC.parent / "local" if LOCAL_MODE else SRC.parent
LOCAL: dict = json.loads((SRC / "local.json").read_text(encoding="utf-8")) \
    if LOCAL_MODE and (SRC / "local.json").exists() else {}


def cred(tipo: str, chave: str, nome: str) -> dict:
    """Referência de credencial do n8n, só no build local (o id existe apenas na instância local)."""
    return {"credentials": {tipo: {"id": LOCAL[chave], "name": nome}}} if LOCAL.get(chave) else {}

ID_MAIN = "TikTokPostMain01"
ID_AUTH = "TikTokAuthFlow01"
ID_ERRO = "TikTokErrors0001"
ID_MCP = "TikTokMcpServer1"
MEDIA = "http://127.0.0.1:8765"


def _uid(semente: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, semente))


class WF:
    def __init__(self, wid: str, nome: str):
        self.wid, self.nome = wid, nome
        self.nodes: list[dict] = []
        self.conns: dict = {}

    def node(self, nome: str, tipo: str, versao, params: dict, pos: tuple[int, int], **extra) -> str:
        n = {"id": _uid(self.wid + nome), "name": nome, "type": tipo, "typeVersion": versao,
             "position": list(pos), "parameters": params}
        if tipo.endswith(("webhook", "wait", "formTrigger", "mcpTrigger")) or "sendAndWait" in json.dumps(params):
            n["webhookId"] = _uid(self.wid + nome + "hook")
        n.update(extra)
        self.nodes.append(n)
        return nome

    def link(self, de: str, para: str, saida: int = 0, tipo: str = "main") -> None:
        lst = self.conns.setdefault(de, {}).setdefault(tipo, [])
        while len(lst) <= saida:
            lst.append([])
        lst[saida].append({"node": para, "type": tipo, "index": 0})

    def salvar(self, arquivo: str, settings: dict | None = None) -> None:
        wf = {"id": self.wid, "name": self.nome, "nodes": self.nodes, "connections": self.conns,
              "active": False, "settings": {"executionOrder": "v1", **(settings or {})},
              "pinData": {}, "meta": {"templateCredsSetupCompleted": False}, "tags": []}
        OUT.mkdir(exist_ok=True)
        (OUT / arquivo).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print("gerado", arquivo)


# ------------------------------------------------------------ helpers de nós
def set_node(campos: list[tuple[str, object, str]], incluir_outros: bool = False) -> dict:
    return {"assignments": {"assignments": [
        {"id": _uid(n + str(v)), "name": n, "value": v, "type": t} for n, v, t in campos]},
        "includeOtherFields": incluir_outros, "options": {}}


def if_node(esquerda: str, operador: dict, direita=None) -> dict:
    cond = {"id": _uid(esquerda), "leftValue": esquerda, "operator": operador}
    if direita is not None:
        cond["rightValue"] = direita
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                                       "version": 2},
                           "conditions": [cond], "combinator": "and"}, "options": {}}


VERDADEIRO = {"type": "boolean", "operation": "true", "singleValue": True}
IGUAL = {"type": "string", "operation": "equals"}
NAO_VAZIO = {"type": "string", "operation": "notEmpty", "singleValue": True}


def http(metodo: str, url: str, corpo_json: str | None = None, headers: list[tuple[str, str]] | None = None,
         **opcoes) -> dict:
    p: dict = {"method": metodo, "url": url, "options": opcoes.pop("options", {})}
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers]}
    if corpo_json is not None:
        p.update(sendBody=True, specifyBody="json", jsonBody=corpo_json)
    p.update(opcoes)
    return p


def tiktok_headers() -> list[tuple[str, str]]:
    return [("Authorization", "=Bearer {{ $('Token TikTok válido').first().json.access_token }}"),
            ("Content-Type", "application/json; charset=UTF-8")]


def tiktok_url(rota: str) -> str:
    return "={{ $('Token TikTok válido').first().json.api_base }}" + rota


# =============================================================== MAIN
def workflow_principal() -> None:
    w = WF(ID_MAIN, "TikTok · Post automático com IA")
    banco = (SRC / "banco_roteiros.js").read_text(encoding="utf-8")
    prompt = (SRC / "prompt_roteiro.md").read_text(encoding="utf-8")

    w.node("Testar agora", "n8n-nodes-base.manualTrigger", 1, {}, (0, 0))
    w.node("Agendado (diário 11h)", "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"triggerAtHour": 11}]}}, (0, 160))
    w.node("Formulário (tema manual)", "n8n-nodes-base.formTrigger", 2.2,
           {"formTitle": "Novo post no TikTok", "formDescription": "Gera roteiro, vídeo e publica. Deixe vazio para tema automático.",
            "formFields": {"values": [{"fieldLabel": "tema", "placeholder": "ex.: golpe do boleto"}]},
            "options": {}}, (0, 320))
    w.node("Chamado via MCP / outro workflow", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
           {"inputSource": "workflowInputs", "workflowInputs": {"values": [{"name": "tema"}]}}, (0, 480))

    w.node("Config", "n8n-nodes-base.set", 3.4, set_node([
        ("tema", "={{ ($json.tema || '').toString().trim() }}", "string"),
        ("usar_ia", True, "boolean"),
        ("provedor_ia", LOCAL.get("provedor_ia", "openrouter"), "string"),
        ("modelo_openrouter", LOCAL.get("modelo_openrouter", "nvidia/nemotron-3-super-120b-a12b:free"), "string"),
        ("modelo", "claude-opus-5-5", "string"),
        ("media_api", MEDIA, "string"),
        ("privacidade_preferida", "SELF_ONLY", "string"),
        ("exigir_aprovacao", bool(LOCAL.get("exigir_aprovacao", False)), "boolean"),
        ("telegram_chat_id", str(LOCAL.get("telegram_chat_id", "")), "string"),
        ("marca", "@automacao.na.pratica", "string"),
    ]), (260, 240), notes="Painel de controle. provedor_ia: openrouter (gratuito) ou anthropic. Sem credencial, "
                          "a IA falha e o banco de roteiros assume. exigir_aprovacao liga a revisão via Telegram.")
    for t in ("Testar agora", "Agendado (diário 11h)", "Formulário (tema manual)", "Chamado via MCP / outro workflow"):
        w.link(t, "Config")

    w.node("Usar IA?", "n8n-nodes-base.if", 2.2, if_node("={{ $json.usar_ia }}", VERDADEIRO), (480, 240))
    w.link("Config", "Usar IA?")
    w.node("Provedor: Claude?", "n8n-nodes-base.if", 2.2,
           if_node("={{ $json.provedor_ia }}", IGUAL, "anthropic"), (600, 120))
    w.link("Usar IA?", "Provedor: Claude?", 0)

    schema_roteiro = {
        "type": "object", "additionalProperties": False,
        "required": ["tema", "gancho", "cenas", "cta", "hashtags"],
        "properties": {
            "tema": {"type": "string"},
            "gancho": {"type": "string", "description": "Frase de até 12 palavras para prender nos 2 primeiros segundos"},
            "cenas": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["texto", "narracao"],
                "properties": {"texto": {"type": "string", "description": "Texto na tela, até 8 palavras"},
                               "narracao": {"type": "string", "description": "Fala da cena, 1 a 2 frases"}}}},
            "cta": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        }}
    corpo_openrouter = (
        "={{ JSON.stringify({\n"
        "  model: $('Config').first().json.modelo_openrouter,\n"
        "  temperature: 0.8,\n"
        "  response_format: { type: 'json_schema', json_schema: { name: 'roteiro', schema: "
        + json.dumps(schema_roteiro, ensure_ascii=False) + " } },\n"
        "  messages: [\n"
        "    { role: 'system', content: " + json.dumps(prompt + "\n\nResponda SOMENTE com o JSON do roteiro.",
                                                      ensure_ascii=False) + " },\n"
        "    { role: 'user', content: 'Tema: ' + ($('Config').first().json.tema || "
        "'escolha um tema útil de automação para empresas') }\n"
        "  ]\n"
        "}) }}"
    )
    w.node("OpenRouter: gerar roteiro", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "https://openrouter.ai/api/v1/chat/completions", corpo_openrouter,
        [("X-Title", "Case GoGroup - TikTok automatico")],
        authentication="genericCredentialType", genericAuthType="httpHeaderAuth",
        options={"timeout": 120000}),
        (840, 200), onError="continueErrorOutput", retryOnFail=True, maxTries=2, waitBetweenTries=3000,
        notes="Modelo gratuito via OpenRouter (credencial Header Auth 'OpenRouter'). Falhou? banco de roteiros.",
        **cred("httpHeaderAuth", "openrouter_cred_id", "OpenRouter"))
    w.link("Provedor: Claude?", "OpenRouter: gerar roteiro", 1)
    w.node("Ler resposta (OpenRouter)", "n8n-nodes-base.code", 2, {"jsCode": (
        "const r = $json;\n"
        "if (r.error) throw new Error('OpenRouter: ' + JSON.stringify(r.error));\n"
        "const texto = r.choices?.[0]?.message?.content || '';\n"
        "const m = texto.match(/\\{[\\s\\S]*\\}/);\n"
        "if (!m) throw new Error('Resposta sem JSON');\n"
        "return [{ json: { ...JSON.parse(m[0]), origem: 'ia:' + (r.model || 'openrouter'),\n"
        "  tokens: r.usage?.total_tokens || 0 } }];\n")},
        (1060, 200), onError="continueErrorOutput")
    w.link("OpenRouter: gerar roteiro", "Ler resposta (OpenRouter)", 0)

    corpo_claude = (
        "={{ JSON.stringify({\n"
        "  model: $json.modelo,\n"
        "  max_tokens: 4000,\n"
        "  fallbacks: 'default',\n"
        "  output_config: { effort: 'low', format: { type: 'json_schema', schema: "
        + json.dumps(schema_roteiro, ensure_ascii=False) + " } },\n"
        "  system: " + json.dumps(prompt, ensure_ascii=False) + ",\n"
        "  messages: [{ role: 'user', content: 'Tema: ' + ($json.tema || 'escolha um tema útil de automação para empresas') }]\n"
        "}) }}"
    )
    w.node("Claude: gerar roteiro", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "https://api.anthropic.com/v1/messages", corpo_claude,
        [("anthropic-version", "2023-06-01"), ("anthropic-beta", "server-side-fallback-2026-07-01")],
        authentication="predefinedCredentialType", nodeCredentialType="anthropicApi",
        options={"timeout": 120000}),
        (840, 20), onError="continueErrorOutput", retryOnFail=True, maxTries=2,
        notes="Structured output: a resposta é JSON garantido pelo schema. Falhou? cai no banco de roteiros.")
    w.link("Provedor: Claude?", "Claude: gerar roteiro", 0)

    w.node("Ler resposta da IA", "n8n-nodes-base.code", 2, {"jsCode": (
        "const r = $json;\n"
        "if (r.stop_reason === 'refusal') throw new Error('Claude recusou: ' + JSON.stringify(r.stop_details));\n"
        "if (r.stop_reason === 'max_tokens') throw new Error('Resposta truncada (max_tokens)');\n"
        "const texto = (r.content || []).find(b => b.type === 'text')?.text;\n"
        "if (!texto) throw new Error('Resposta sem bloco de texto');\n"
        "return [{ json: { ...JSON.parse(texto), origem: 'ia:' + r.model,\n"
        "  tokens: (r.usage?.input_tokens || 0) + (r.usage?.output_tokens || 0) } }];\n")},
        (1060, 20), onError="continueErrorOutput")
    w.link("Claude: gerar roteiro", "Ler resposta da IA", 0)

    w.node("Banco de roteiros", "n8n-nodes-base.code", 2, {"jsCode": banco}, (1060, 400),
           notes="Fallback sem custo: usado com usar_ia=false ou quando a IA falha.")
    w.link("Usar IA?", "Banco de roteiros", 1)
    w.link("Claude: gerar roteiro", "Banco de roteiros", 1)
    w.link("Ler resposta da IA", "Banco de roteiros", 1)
    w.link("OpenRouter: gerar roteiro", "Banco de roteiros", 1)
    w.link("Ler resposta (OpenRouter)", "Banco de roteiros", 1)

    w.node("Normalizar roteiro", "n8n-nodes-base.code", 2, {"jsCode": (
        "const cfg = $('Config').first().json;\n"
        "const r = $json;\n"
        "const limpa = (s, n) => (s || '').toString().replace(/\\s+/g, ' ').trim().slice(0, n);\n"
        "const cenas = (r.cenas || []).slice(0, 5).map(c => ({ texto: limpa(c.texto, 90), narracao: limpa(c.narracao || c.texto, 300) }))\n"
        "  .filter(c => c.texto);\n"
        "if (!r.gancho || cenas.length < 2) throw new Error('Roteiro inválido: precisa de gancho e ao menos 2 cenas');\n"
        "const hashtags = [...new Set((r.hashtags || []).map(h => '#' + h.replace(/^#/, '').replace(/\\s+/g, '')))].slice(0, 6);\n"
        "const titulo = (limpa(r.gancho, 150) + '\\n\\n' + hashtags.join(' ')).slice(0, 2200);\n"
        "return [{ json: { tema: r.tema || cfg.tema, gancho: limpa(r.gancho, 100), cenas, cta: limpa(r.cta, 90),\n"
        "  hashtags, titulo, marca: cfg.marca, origem: r.origem } }];\n")}, (1300, 240))
    w.link("Ler resposta da IA", "Normalizar roteiro", 0)
    w.link("Ler resposta (OpenRouter)", "Normalizar roteiro", 0)
    w.link("Banco de roteiros", "Normalizar roteiro", 0)

    w.node("Renderizar vídeo", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $('Config').first().json.media_api }}/render", "={{ JSON.stringify($json) }}",
        options={"timeout": 300000}), (1440, 240),
        notes="Serviço local: TTS neural pt-BR + slides 1080x1920 + ffmpeg (H.264/AAC).")
    w.link("Normalizar roteiro", "Renderizar vídeo")

    w.node("Exigir aprovação?", "n8n-nodes-base.if", 2.2,
           if_node("={{ $('Config').first().json.exigir_aprovacao }}", VERDADEIRO), (1660, 240))
    w.link("Renderizar vídeo", "Exigir aprovação?")

    # --- aprovação humana (Telegram)
    w.node("Baixar prévia", "n8n-nodes-base.httpRequest", 4.2, http(
        "GET", "={{ $('Renderizar vídeo').first().json.video_url }}",
        options={"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}), (1880, 0))
    w.link("Exigir aprovação?", "Baixar prévia", 0)
    w.node("Telegram: enviar prévia", "n8n-nodes-base.telegram", 1.2, {
        "operation": "sendVideo", "chatId": "={{ $('Config').first().json.telegram_chat_id }}",
        "binaryData": True, "binaryPropertyName": "data",
        "additionalFields": {"caption": "={{ $('Normalizar roteiro').first().json.titulo }}"}}, (2100, 0),
        disabled=not LOCAL.get("telegram_cred_id"),
        notes="Ative após criar a credencial do bot (BotFather) e preencher telegram_chat_id.",
        **cred("telegramApi", "telegram_cred_id", "Telegram"))
    w.link("Baixar prévia", "Telegram: enviar prévia")
    w.node("Telegram: aprovar?", "n8n-nodes-base.telegram", 1.2, {
        "operation": "sendAndWait", "chatId": "={{ $('Config').first().json.telegram_chat_id }}",
        "message": "=Publicar este vídeo no TikTok?\nTema: {{ $('Normalizar roteiro').first().json.tema }}",
        "approvalOptions": {"values": {"approvalType": "double", "approveLabel": "Publicar",
                                       "disapproveLabel": "Descartar"}},
        "options": {"limitWaitTime": {"values": {"limitType": "afterTimeInterval", "resumeAmount": 12,
                                                 "resumeUnit": "hours"}}}}, (2320, 0),
        disabled=not LOCAL.get("telegram_cred_id"), notes="Human-in-the-loop: aprova ou descarta antes de publicar.",
        **cred("telegramApi", "telegram_cred_id", "Telegram"))
    w.link("Telegram: enviar prévia", "Telegram: aprovar?")
    w.node("Aprovado?", "n8n-nodes-base.if", 2.2, if_node("={{ $json.data?.approved }}", VERDADEIRO), (2540, 0))
    w.link("Telegram: aprovar?", "Aprovado?")
    w.node("Registrar descarte", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $('Config').first().json.media_api }}/log",
        "={{ JSON.stringify({ tema: $('Normalizar roteiro').first().json.tema, titulo: $('Normalizar roteiro').first().json.gancho, status: 'DESCARTADO', video: $('Renderizar vídeo').first().json.video_url, modo: 'aprovacao' }) }}"),
        (2760, 100))
    w.link("Aprovado?", "Registrar descarte", 1)

    # --- publicação
    w.node("Token TikTok válido", "n8n-nodes-base.executeWorkflow", 1.2, {
        "workflowId": {"__rl": True, "value": ID_AUTH, "mode": "id"},
        "workflowInputs": {"mappingMode": "defineBelow", "value": {}, "matchingColumns": [], "schema": [],
                           "attemptToConvertTypes": False, "convertFieldsToString": True},
        "options": {"waitForSubWorkflow": True}}, (2760, 300),
        notes="Subworkflow: devolve access_token válido (renova com refresh_token) e a base da API.")
    w.link("Exigir aprovação?", "Token TikTok válido", 1)
    w.link("Aprovado?", "Token TikTok válido", 0)

    w.node("Consultar criador", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", tiktok_url("/v2/post/publish/creator_info/query/"), "={}", tiktok_headers()), (2980, 300),
        notes="Exigência do TikTok: consultar opções de privacidade antes de postar.")
    w.link("Token TikTok válido", "Consultar criador")

    w.node("Preparar post", "n8n-nodes-base.code", 2, {"jsCode": (
        "const cfg = $('Config').first().json;\n"
        "const info = $json.data || {};\n"
        "const opcoes = info.privacy_level_options || [];\n"
        "if (!opcoes.length) throw new Error('TikTok não retornou opções de privacidade');\n"
        "// app não auditado só tem SELF_ONLY; usamos a preferida se estiver disponível\n"
        "const privacidade = opcoes.includes(cfg.privacidade_preferida) ? cfg.privacidade_preferida : opcoes[0];\n"
        "const tam = $('Renderizar vídeo').first().json.tamanho_bytes;\n"
        "const corpo = {\n"
        "  post_info: { title: $('Normalizar roteiro').first().json.titulo, privacy_level: privacidade,\n"
        "    disable_duet: !!info.duet_disabled, disable_comment: !!info.comment_disabled,\n"
        "    disable_stitch: !!info.stitch_disabled, video_cover_timestamp_ms: 1000, is_aigc: true },\n"
        "  source_info: { source: 'FILE_UPLOAD', video_size: tam, chunk_size: tam, total_chunk_count: 1 },\n"
        "};\n"
        "return [{ json: { privacidade, conta: info.creator_username, corpo } }];\n")}, (3090, 300))
    w.link("Consultar criador", "Preparar post")
    w.node("Iniciar publicação", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", tiktok_url("/v2/post/publish/video/init/"), "={{ JSON.stringify($json.corpo) }}",
        tiktok_headers(), options={"response": {"response": {"neverError": True}}}), (3200, 300),
        notes="Direct Post, FILE_UPLOAD em 1 chunk (vídeo < 64 MB). is_aigc=true: conteúdo gerado por IA.")
    w.link("Preparar post", "Iniciar publicação")

    # O TikTok devolve o motivo da recusa em error.code; traduzimos os casos comuns em ação concreta.
    w.node("Conferir início", "n8n-nodes-base.code", 2, {"jsCode": (
        "const e = $json.error || {};\n"
        "if (e.code === 'ok' && $json.data?.upload_url) return [$input.first()];\n"
        "const dicas = {\n"
        "  unaudited_client_can_only_post_to_private_accounts: 'App sem auditoria só publica em CONTA PRIVADA: no TikTok, Configurações e privacidade > Privacidade > Conta privada.',\n"
        "  access_token_invalid: 'Token inválido ou revogado: refaça o login em /webhook/tiktok/login.',\n"
        "  scope_not_authorized: 'Falta a permissão video.publish: adicione o escopo no app e refaça o login.',\n"
        "  spam_risk_too_many_posts: 'Limite diário de posts do TikTok atingido: tente amanhã.',\n"
        "  rate_limit_exceeded: 'Limite de chamadas da API (6/min): aguarde um minuto.',\n"
        "  privacy_level_option_mismatch: 'Privacidade escolhida não está entre as opções da conta.',\n"
        "};\n"
        "throw new Error('TikTok recusou a publicação (' + (e.code || 'sem código') + '). ' + (dicas[e.code] || e.message || ''));\n")},
        (3310, 300))
    w.link("Iniciar publicação", "Conferir início")

    w.node("Baixar vídeo", "n8n-nodes-base.httpRequest", 4.2, http(
        "GET", "={{ $('Renderizar vídeo').first().json.video_url }}",
        options={"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}), (3420, 300))
    w.link("Conferir início", "Baixar vídeo")

    w.node("Enviar vídeo (PUT)", "n8n-nodes-base.httpRequest", 4.2, http(
        "PUT", "={{ $('Iniciar publicação').first().json.data.upload_url }}", None,
        [("Content-Type", "video/mp4"),
         ("Content-Range", "=bytes 0-{{ $('Renderizar vídeo').first().json.tamanho_bytes - 1 }}/{{ $('Renderizar vídeo').first().json.tamanho_bytes }}")],
        sendBody=True, contentType="binaryData", inputDataFieldName="data"), (3640, 300))
    w.link("Baixar vídeo", "Enviar vídeo (PUT)")

    w.node("Aguardar processamento", "n8n-nodes-base.wait", 1.1, {"amount": 5, "unit": "seconds"}, (3860, 300))
    w.link("Enviar vídeo (PUT)", "Aguardar processamento")

    w.node("Consultar status", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", tiktok_url("/v2/post/publish/status/fetch/"),
        "={{ JSON.stringify({ publish_id: $('Iniciar publicação').first().json.data.publish_id }) }}",
        tiktok_headers()), (4080, 300))
    w.link("Aguardar processamento", "Consultar status")

    w.node("Publicado?", "n8n-nodes-base.if", 2.2,
           if_node("={{ $json.data.status }}", IGUAL, "PUBLISH_COMPLETE"), (4300, 300))
    w.link("Consultar status", "Publicado?")

    w.node("Falhou ou esgotou?", "n8n-nodes-base.if", 2.2, if_node(
        "={{ $json.data.status === 'FAILED' || $runIndex >= 24 }}", VERDADEIRO), (4520, 440))
    w.link("Publicado?", "Falhou ou esgotou?", 1)
    w.link("Falhou ou esgotou?", "Aguardar processamento", 1)
    w.node("Erro na publicação", "n8n-nodes-base.stopAndError", 1, {
        "errorMessage": "=Publicação falhou: status {{ $json.data.status }} {{ $json.data.fail_reason || '' }}"},
        (4740, 440))
    w.link("Falhou ou esgotou?", "Erro na publicação", 0)

    corpo_log = (
        "={{ JSON.stringify({\n"
        "  tema: $('Normalizar roteiro').first().json.tema,\n"
        "  titulo: $('Normalizar roteiro').first().json.gancho,\n"
        "  publish_id: $('Iniciar publicação').first().json.data.publish_id,\n"
        "  status: $json.data.status,\n"
        "  privacidade: $('Preparar post').first().json.privacidade,\n"
        "  video: $('Renderizar vídeo').first().json.video_url,\n"
        "  modo: $('Token TikTok válido').first().json.api_base.includes('mock') ? 'simulador' : 'api-real'\n"
        "}) }}")
    w.node("Registrar no log", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $('Config').first().json.media_api }}/log", corpo_log), (4520, 200))
    w.link("Publicado?", "Registrar no log", 0)

    w.node("Resultado", "n8n-nodes-base.set", 3.4, set_node([
        ("ok", True, "boolean"),
        ("status", "={{ $('Consultar status').last().json.data.status }}", "string"),
        ("publish_id", "={{ $('Iniciar publicação').first().json.data.publish_id }}", "string"),
        ("tema", "={{ $('Normalizar roteiro').first().json.tema }}", "string"),
        ("legenda", "={{ $('Normalizar roteiro').first().json.titulo }}", "string"),
        ("privacidade", "={{ $('Preparar post').first().json.privacidade }}", "string"),
        ("roteiro_origem", "={{ $('Normalizar roteiro').first().json.origem }}", "string"),
        ("video_url", "={{ $('Renderizar vídeo').first().json.video_url }}", "string"),
        ("duracao_seg", "={{ $('Renderizar vídeo').first().json.duracao_seg }}", "number"),
        ("modo", "={{ $('Token TikTok válido').first().json.api_base.includes('mock') ? 'simulador' : 'api-real' }}", "string"),
    ]), (4740, 200))
    w.link("Registrar no log", "Resultado")

    w.salvar("01_tiktok_post_automatico.json", {"errorWorkflow": ID_ERRO, "callerPolicy": "any"})


# =============================================================== AUTH
def workflow_auth() -> None:
    w = WF(ID_AUTH, "TikTok · Autenticação (OAuth + token)")
    w.node("GET /tiktok/login", "n8n-nodes-base.webhook", 2,
           {"httpMethod": "GET", "path": "tiktok/login", "responseMode": "responseNode", "options": {}}, (0, 0))
    w.node("GET /tiktok/callback", "n8n-nodes-base.webhook", 2,
           {"httpMethod": "GET", "path": "tiktok/callback", "responseMode": "responseNode", "options": {}}, (0, 300))
    w.node("Chamado pelo post (token)", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
           {"inputSource": "passthrough"}, (0, 600))

    cfg = [
        ("client_key", LOCAL.get("tiktok_client_key", "PREENCHER_CLIENT_KEY"), "string"),
        ("client_secret", LOCAL.get("tiktok_client_secret", "PREENCHER_CLIENT_SECRET"), "string"),
        ("redirect_uri", LOCAL.get("tiktok_redirect_uri", "https://SEU-TUNEL.trycloudflare.com/webhook/tiktok/callback"), "string"),
        ("scopes", "user.info.basic,video.publish", "string"),
        ("api_base", LOCAL.get("tiktok_api_base", f"{MEDIA}/mock-tiktok"), "string"),
        ("media_api", MEDIA, "string"),
        ("state", "case-gogroup-csrf", "string"),
    ]
    for i, entrada in enumerate(("GET /tiktok/login", "GET /tiktok/callback", "Chamado pelo post (token)")):
        nome = ["Config (login)", "Config (callback)", "Config (token)"][i]
        w.node(nome, "n8n-nodes-base.set", 3.4, set_node(cfg, incluir_outros=True), (240, i * 300),
               notes="api_base: simulador local ou https://open.tiktokapis.com (API real). "
                     "Credenciais do app do TikTok for Developers (sandbox).")
        w.link(entrada, nome)

    # login -> redireciona para a tela de autorização do TikTok
    w.node("Redirecionar para TikTok", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "redirect",
        "redirectURL": "=https://www.tiktok.com/v2/auth/authorize/?client_key={{ $json.client_key }}"
                       "&scope={{ encodeURIComponent($json.scopes) }}&response_type=code"
                       "&redirect_uri={{ encodeURIComponent($json.redirect_uri) }}&state={{ $json.state }}",
        "options": {}}, (480, 0))
    w.link("Config (login)", "Redirecionar para TikTok")

    # callback -> troca code por token e guarda
    w.node("State e code ok?", "n8n-nodes-base.if", 2.2, {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
        "conditions": [
            {"id": _uid("st"), "leftValue": "={{ $json.query.state }}", "rightValue": "={{ $json.state }}",
             "operator": IGUAL},
            {"id": _uid("cd"), "leftValue": "={{ $json.query.code }}", "operator": NAO_VAZIO}],
        "combinator": "and"}, "options": {}}, (480, 300))
    w.link("Config (callback)", "State e code ok?")
    w.node("Trocar code por token", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $json.api_base }}/v2/oauth/token/", None,
        [("Content-Type", "application/x-www-form-urlencoded")],
        sendBody=True, contentType="form-urlencoded", bodyParameters={"parameters": [
            {"name": "client_key", "value": "={{ $json.client_key }}"},
            {"name": "client_secret", "value": "={{ $json.client_secret }}"},
            {"name": "code", "value": "={{ $json.query.code }}"},
            {"name": "grant_type", "value": "authorization_code"},
            {"name": "redirect_uri", "value": "={{ $json.redirect_uri }}"}]}), (720, 240))
    w.link("State e code ok?", "Trocar code por token", 0)
    w.node("Guardar tokens", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $('Config (callback)').first().json.media_api }}/tokens",
        "={{ JSON.stringify({ ...$json, api_base: $('Config (callback)').first().json.api_base }) }}"), (960, 240))
    w.link("Trocar code por token", "Guardar tokens")
    w.node("Conta conectada", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text",
        "responseBody": "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                        "<h1>✅ Conta TikTok conectada</h1><p>Pode fechar esta aba e rodar o workflow de post.</p>"
                        "</body></html>",
        "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}},
        (1200, 240))
    w.link("Guardar tokens", "Conta conectada")
    w.node("Callback inválido", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text", "responseBody": "Callback inválido (state/code ausente ou incorreto).",
        "options": {"responseCode": 400}}, (720, 400))
    w.link("State e code ok?", "Callback inválido", 1)

    # token: lê, renova se preciso, devolve
    w.node("Ler tokens", "n8n-nodes-base.httpRequest", 4.2, http(
        "GET", "={{ $json.media_api }}/tokens"), (480, 600))
    w.link("Config (token)", "Ler tokens")
    w.node("Conta conectada?", "n8n-nodes-base.if", 2.2,
           if_node("={{ $json.refresh_token || $json.access_token || '' }}", NAO_VAZIO), (720, 600))
    w.link("Ler tokens", "Conta conectada?")
    w.node("Conta não conectada", "n8n-nodes-base.stopAndError", 1, {
        "errorMessage": "Conta TikTok não conectada: abra <N8N_WEBHOOK_URL>/webhook/tiktok/login e autorize."},
        (960, 760))
    w.link("Conta conectada?", "Conta não conectada", 1)
    w.node("Token ainda vale?", "n8n-nodes-base.if", 2.2, if_node(
        "={{ ($json.expira_em || 0) - Math.floor(Date.now() / 1000) > 300 }}", VERDADEIRO), (960, 600))
    w.link("Conta conectada?", "Token ainda vale?", 0)
    w.node("Renovar token", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $json.api_base }}/v2/oauth/token/", None,
        [("Content-Type", "application/x-www-form-urlencoded")],
        sendBody=True, contentType="form-urlencoded", bodyParameters={"parameters": [
            {"name": "client_key", "value": "={{ $('Config (token)').first().json.client_key }}"},
            {"name": "client_secret", "value": "={{ $('Config (token)').first().json.client_secret }}"},
            {"name": "grant_type", "value": "refresh_token"},
            {"name": "refresh_token", "value": "={{ $json.refresh_token }}"}]}), (1200, 700))
    w.link("Token ainda vale?", "Renovar token", 1)
    w.node("Guardar token renovado", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", "={{ $('Config (token)').first().json.media_api }}/tokens",
        "={{ JSON.stringify({ ...$json, api_base: $('Ler tokens').first().json.api_base }) }}"), (1440, 700))
    w.link("Renovar token", "Guardar token renovado")
    w.node("Token renovado", "n8n-nodes-base.set", 3.4, set_node([
        ("access_token", "={{ $('Renovar token').first().json.access_token }}", "string"),
        ("api_base", "={{ $('Ler tokens').first().json.api_base }}", "string")]), (1680, 700))
    w.link("Guardar token renovado", "Token renovado")
    w.node("Token atual", "n8n-nodes-base.set", 3.4, set_node([
        ("access_token", "={{ $json.access_token }}", "string"),
        ("api_base", "={{ $json.api_base }}", "string")]), (1200, 540))
    w.link("Token ainda vale?", "Token atual", 0)

    w.salvar("02_tiktok_autenticacao.json", {"callerPolicy": "workflowsFromSameOwner"})


# =============================================================== ERROS
def workflow_erros() -> None:
    w = WF(ID_ERRO, "TikTok · Tratamento de erros")
    w.node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}, (0, 0))
    w.node("Registrar erro", "n8n-nodes-base.httpRequest", 4.2, http(
        "POST", f"{MEDIA}/log",
        "={{ JSON.stringify({ status: 'ERRO', modo: $json.workflow.name, "
        "erro: ($json.execution.lastNodeExecuted || '') + ': ' + ($json.execution.error?.message || 'desconhecido'), "
        "video: $json.execution.url || '' }) }}"), (240, 0),
        notes="Também é o ponto para plugar alerta (Telegram/Slack/e-mail).")
    w.link("Error Trigger", "Registrar erro")
    w.salvar("03_tiktok_erros.json")


# =============================================================== MCP
def workflow_mcp() -> None:
    w = WF(ID_MCP, "TikTok · Servidor MCP")
    w.node("MCP Server Trigger", "@n8n/n8n-nodes-langchain.mcpTrigger", 2, {"path": "tiktok"}, (0, 0),
           notes="Endpoint MCP: <n8n>/mcp/tiktok. Conecte no Claude Code/Desktop.")
    w.node("criar_post_tiktok", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, {
        "description": "Cria e publica um vídeo curto no TikTok sobre o tema informado: gera roteiro, "
                       "narração e vídeo 9:16 e publica pela Content Posting API. Retorna status, publish_id e "
                       "legenda. Pode levar cerca de 1 minuto.",
        "workflowId": {"__rl": True, "value": ID_MAIN, "mode": "id"},
        "workflowInputs": {"mappingMode": "defineBelow",
                           "value": {"tema": "={{ $fromAI('tema', 'Tema do vídeo, ex.: golpe do boleto. Vazio = automático', 'string') }}"},
                           "matchingColumns": [], "schema": [{
                               "id": "tema", "displayName": "tema", "required": False, "defaultMatch": False,
                               "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False}],
                           "attemptToConvertTypes": False, "convertFieldsToString": False}}, (-200, 240))
    w.link("criar_post_tiktok", "MCP Server Trigger", tipo="ai_tool")
    w.node("historico_publicacoes", "n8n-nodes-base.httpRequestTool", 4.2, {
        "toolDescription": "Lista as publicações já feitas (data, tema, status, publish_id, modo).",
        "url": f"{MEDIA}/log", "options": {}}, (200, 240))
    w.link("historico_publicacoes", "MCP Server Trigger", tipo="ai_tool")
    w.salvar("04_tiktok_mcp_server.json")


if __name__ == "__main__":
    workflow_principal()
    workflow_auth()
    workflow_erros()
    workflow_mcp()
