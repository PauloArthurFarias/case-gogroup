# Importa os workflows no n8n local (rode com o n8n PARADO na primeira vez).
param([string]$NodeDir = "$env:USERPROFILE\tools\node24", [string]$N8nDir = "$env:USERPROFILE\tools\n8n")
$env:PATH = "$NodeDir;$env:PATH"
& "$N8nDir\node_modules\.bin\n8n.cmd" import:workflow --separate --input="$PSScriptRoot\workflows"
Write-Host "Pronto. Inicie com .\iniciar.ps1, abra http://localhost:5678 e clique em Publish em cada workflow."
