# Atalho de demonstracao do Case GoGroup.
# Uso:  .\demo.ps1               (sobe os dois desafios)
#       .\demo.ps1 -Somente d1   (so o painel do agente de Contas a Pagar)
#       .\demo.ps1 -Somente d2   (so o n8n + servico de midia do TikTok)
# Dica: em maquinas com pouca memoria, demonstre um desafio por vez.
param([ValidateSet("todos", "d1", "d2")][string]$Somente = "todos")
$ErrorActionPreference = "Stop"
$raiz = $PSScriptRoot

function Esperar($url, $segundos) {
    for ($i = 0; $i -lt $segundos; $i++) {
        try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep 1 }
    }
    return $false
}

# O n8n responde /healthz antes de registrar os webhooks dos workflows publicados (~20 s depois).
# O callback sem parametros responde 400 quando registrado e 404 enquanto ainda nao esta.
function EsperarWebhooks($segundos) {
    for ($i = 0; $i -lt $segundos; $i++) {
        try { Invoke-WebRequest -Uri "http://127.0.0.1:5678/webhook/tiktok/callback" -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true }
        catch {
            $r = $_.Exception.Response
            if ($r -and [int]$r.StatusCode -ne 404) { return $true }
            Start-Sleep 1
        }
    }
    return $false
}

if ($Somente -in "todos", "d1") {
    $d1 = Join-Path $raiz "desafio1-agente-nf"
    Write-Host "[D1] Gerando documentos ficticios na inbox..."
    Push-Location $d1
    python scripts\gerar_dados_ficticios.py --limpar
    Pop-Location
    Write-Host "[D1] Subindo painel Streamlit (nova janela)..."
    Start-Process -FilePath "python" -ArgumentList "-m streamlit run dashboard.py --server.headless true --server.port 8501" -WorkingDirectory $d1
    if (Esperar "http://127.0.0.1:8501/_stcore/health" 60) { Start-Process "http://localhost:8501" }
    else { Write-Warning "Painel nao respondeu em 60 s; veja a janela do Streamlit." }
}

if ($Somente -in "todos", "d2") {
    $d2 = Join-Path $raiz "desafio2-tiktok-n8n"
    Write-Host "[D2] Subindo servico de midia + n8n (nova janela)..."
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$d2\iniciar.ps1`"" -WorkingDirectory $d2
    if ((Esperar "http://127.0.0.1:5678/healthz" 180) -and (EsperarWebhooks 90)) {
        Start-Process "http://localhost:5678"
        Start-Process "http://127.0.0.1:8765/log"
        Write-Host "[D2] n8n pronto. Login: admin@case.local / CaseGoGroup2026!"
    } else { Write-Warning "n8n nao respondeu em 3 min; veja a janela do n8n." }
}

Write-Host "`nRoteiro da demonstracao: COMO_DEMONSTRAR.md"
