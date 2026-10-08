# Abre um tunel HTTPS gratuito (Cloudflare quick tunnel) ate o n8n local e devolve o endereco publico.
# Usado pelo iniciar.ps1: o endereco vira o N8N_WEBHOOK_URL, que o n8n usa nos botoes do Telegram
# (Publicar / Descartar). Cada tunel novo tem outro endereco, por isso ele e aberto a cada inicio.
# Retorna um objeto { Url, Processo } ou $null se nao conseguir.
param(
    [string]$Cloudflared = "$env:USERPROFILE\tools\cloudflared.exe",
    [int]$Porta = 5678,
    [int]$Espera = 45
)

if (-not (Test-Path $Cloudflared)) { return $null }

# Tuneis antigos deste projeto (mesma porta) ficariam orfaos: encerra antes de abrir outro.
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
    Where-Object { $_.CommandLine -match "localhost:$Porta" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$log = Join-Path $env:TEMP "case-gogroup-tunel.log"
Remove-Item $log -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $Cloudflared -ArgumentList "tunnel --no-autoupdate --url http://localhost:$Porta" `
    -WindowStyle Hidden -RedirectStandardError $log -PassThru

for ($i = 0; $i -lt $Espera; $i++) {
    Start-Sleep 1
    if ($p.HasExited) { break }
    $texto = try { Get-Content $log -Raw -ErrorAction Stop } catch { "" }
    # Pronto quando o endereco foi criado E o tunel registrou a conexao com a Cloudflare. Nao consultamos o
    # DNS antes disso: um "nao existe" consultado cedo demais fica em cache no Windows por alguns minutos.
    if ($texto -match 'https://[a-z0-9-]+\.trycloudflare\.com' -and $texto -match 'Registered tunnel connection') {
        $url = [regex]::Match($texto, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
        Start-Sleep 3
        return [pscustomobject]@{ Url = $url; Processo = $p }
    }
}

Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
return $null
