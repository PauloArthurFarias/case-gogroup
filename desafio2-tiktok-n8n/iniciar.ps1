# Sobe o servico de midia e o n8n local (Node 24 portatil).
# Uso:  .\iniciar.ps1                 (n8n em http://localhost:5678)
#       $env:N8N_WEBHOOK_URL="https://xxx.trycloudflare.com/"; .\iniciar.ps1   (com tunel para o OAuth)
param(
    [string]$NodeDir = "$env:USERPROFILE\tools\node24",
    [string]$N8nDir  = "$env:USERPROFILE\tools\n8n"
)
$ErrorActionPreference = "Stop"
$aqui = $PSScriptRoot

if (-not (Test-Path "$NodeDir\node.exe")) { throw "Node 24 nao encontrado em $NodeDir (veja README)." }
$env:PATH = "$NodeDir;$env:PATH"

# Servico de midia (render de video, tokens, log, simulador TikTok) em segundo plano
Start-Process -FilePath "python" -ArgumentList "`"$aqui\media_service\server.py`"" -WindowStyle Minimized

# Configuracao do n8n
$env:N8N_PORT = "5678"
$env:GENERIC_TIMEZONE = "America/Sao_Paulo"
$env:TZ = "America/Sao_Paulo"
$env:N8N_DEFAULT_LOCALE = "en"
$env:N8N_DIAGNOSTICS_ENABLED = "false"
if (-not $env:N8N_WEBHOOK_URL) { $env:N8N_WEBHOOK_URL = "http://localhost:5678/" }

& "$N8nDir\node_modules\.bin\n8n.cmd" start
