# Sobe o servico de midia e o n8n local (Node 24 portatil).
# Uso:  .\iniciar.ps1              abre um tunel HTTPS novo (tunel.ps1) e usa o endereco dele nos botoes do
#                                  Telegram: aprovar funciona no computador e no celular
#       .\iniciar.ps1 -SemTunel    so localhost: os botoes do Telegram abrem apenas neste computador
#       .\iniciar.ps1 -WebhookUrl "https://meu-dominio/"   endereco publico fixo, se houver um
# O endereco nunca e herdado de uma sessao anterior do PowerShell: um tunel antigo ja fechado deixaria os
# botoes do Telegram apontando para um site que nao existe mais.
param(
    [string]$NodeDir = "$env:USERPROFILE\tools\node24",
    [string]$N8nDir  = "$env:USERPROFILE\tools\n8n",
    [switch]$SemTunel,
    [string]$WebhookUrl = ""
)
$ErrorActionPreference = "Stop"
$aqui = $PSScriptRoot

if (-not (Test-Path "$NodeDir\node.exe")) { throw "Node 24 nao encontrado em $NodeDir (veja README)." }
$env:PATH = "$NodeDir;$env:PATH"

# Servico de midia (render de video, tokens, log, simulador TikTok) em segundo plano
Start-Process -FilePath "python" -ArgumentList "`"$aqui\media_service\server.py`"" -WindowStyle Minimized

# Endereco publico dos webhooks (usado nos links de aprovacao do Telegram)
$tunel = $null
if ($WebhookUrl) {
    $publico = $WebhookUrl.TrimEnd("/") + "/"
} elseif (-not $SemTunel) {
    Write-Host "Abrindo tunel HTTPS para os botoes do Telegram (ate 1 min)..."
    $tunel = & "$aqui\tunel.ps1"
    if ($tunel) {
        $publico = "$($tunel.Url)/"
        Write-Host "Tunel ativo: $($tunel.Url)  (aprovacao funciona no computador e no celular)" -ForegroundColor Green
    } else {
        $publico = "http://localhost:5678/"
        Write-Warning "Tunel nao abriu (sem internet ou cloudflared ausente). Os botoes do Telegram vao abrir so neste computador."
    }
} else {
    $publico = "http://localhost:5678/"
}

# Configuracao do n8n
$env:N8N_PORT = "5678"
$env:GENERIC_TIMEZONE = "America/Sao_Paulo"
$env:TZ = "America/Sao_Paulo"
$env:N8N_DEFAULT_LOCALE = "en"
$env:N8N_DIAGNOSTICS_ENABLED = "false"
$env:N8N_WEBHOOK_URL = $publico
$env:WEBHOOK_URL = $publico
$env:N8N_EDITOR_BASE_URL = "http://localhost:5678/"

try {
    & "$N8nDir\node_modules\.bin\n8n.cmd" start
} finally {
    # Fechar o n8n fecha o tunel junto
    if ($tunel) { Stop-Process -Id $tunel.Processo.Id -Force -ErrorAction SilentlyContinue }
}
