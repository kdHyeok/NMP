[CmdletBinding()]
param(
    [ValidatePattern('^tunnel_(?:[a-z0-9]{4}_)?[a-z0-9]{32}$')]
    [string]$TunnelId = $env:CONTROL_PLANE_TUNNEL_ID,
    [string]$TunnelClient,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Run uv sync --frozen in the repository first.'
}
if (-not $TunnelId) {
    throw 'Pass -TunnelId from https://platform.openai.com/settings/organization/tunnels'
}
if (-not $TunnelClient) {
    $TunnelClient = Join-Path $taskRoot '.tools\tunnel-client\tunnel-client.exe'
    if (-not (Test-Path -LiteralPath $TunnelClient)) { $TunnelClient = 'tunnel-client' }
}
$taskTunnel = (Get-Command $TunnelClient -ErrorAction Stop).Source
$taskEnvNames = @('NAVER_EMAIL_ADDRESS', 'NAVER_EMAIL_PASSWORD', 'CONTROL_PLANE_API_KEY', 'PYTHONUTF8')
$taskSavedEnv = @{}
foreach ($taskName in $taskEnvNames) {
    $taskSavedEnv[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
}

Push-Location -LiteralPath $taskRoot
try {
    if (-not $env:NAVER_EMAIL_ADDRESS) { $env:NAVER_EMAIL_ADDRESS = Read-Host 'Naver email address' }
    if (-not $env:NAVER_EMAIL_PASSWORD -and -not $env:NAVER_EMAIL_PASSWORD_FILE) {
        $taskSecret = Read-Host 'Naver application password (hidden)' -AsSecureString
        $env:NAVER_EMAIL_PASSWORD = [Net.NetworkCredential]::new('', $taskSecret).Password
    }
    if (-not $env:CONTROL_PLANE_API_KEY) {
        $taskSecret = Read-Host 'OpenAI Tunnel runtime API key (hidden)' -AsSecureString
        $env:CONTROL_PLANE_API_KEY = [Net.NetworkCredential]::new('', $taskSecret).Password
    }
    if (-not $env:NAVER_EMAIL_ADDRESS -or (-not $env:NAVER_EMAIL_PASSWORD -and -not $env:NAVER_EMAIL_PASSWORD_FILE) -or -not $env:CONTROL_PLANE_API_KEY) {
        throw 'Email address, application password, and Tunnel runtime key must not be empty.'
    }
    $env:PYTHONUTF8 = '1'
    $taskLocalDir = Join-Path $taskRoot '.tools'
    New-Item -ItemType Directory -Path $taskLocalDir -Force | Out-Null
    $taskCommand = '"' + $taskPython.Replace('\', '/') + '" -B -m naver_mail_mcp.server'
    $taskArgs = @(
        '--control-plane.tunnel-id', $TunnelId,
        '--control-plane.api-key', 'env:CONTROL_PLANE_API_KEY',
        '--mcp.command', $taskCommand,
        '--mcp.max-concurrent-requests', '1',
        '--mcp.stdio-send-initialized-notification',
        '--health.listen-addr', '127.0.0.1:0',
        '--health.url-file', (Join-Path $taskLocalDir 'tunnel-health.url')
    )
    & $taskTunnel doctor @taskArgs --explain
    if ($LASTEXITCODE -ne 0) { throw 'Tunnel doctor failed. Correct the reported configuration before connecting ChatGPT.' }
    if (-not $CheckOnly) {
        & $taskTunnel run @taskArgs
        if ($LASTEXITCODE -ne 0) { throw 'Tunnel client exited with an error.' }
    }
}
finally {
    foreach ($taskName in $taskEnvNames) {
        [Environment]::SetEnvironmentVariable($taskName, $taskSavedEnv[$taskName], 'Process')
    }
    Pop-Location
}
