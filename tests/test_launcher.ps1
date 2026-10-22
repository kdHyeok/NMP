$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('naver-mail-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$taskStub = Join-Path $taskTemp 'tunnel-stub.ps1'
$taskLog = Join-Path $taskTemp 'calls.jsonl'
$taskNames = @('NAVER_EMAIL_ADDRESS', 'NAVER_EMAIL_PASSWORD', 'NAVER_EMAIL_PASSWORD_FILE', 'CONTROL_PLANE_API_KEY', 'PYTHONUTF8', 'NAVER_MCP_TEST_LOG', 'NAVER_MCP_TEST_FAIL')
$taskSaved = @{}
foreach ($taskName in $taskNames) { $taskSaved[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process') }

function Assert-Result([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

try {
    @'
[IO.File]::AppendAllText($env:NAVER_MCP_TEST_LOG, (ConvertTo-Json -InputObject @($args) -Compress) + "`n")
$global:LASTEXITCODE = if ($env:NAVER_MCP_TEST_FAIL) { 7 } else { 0 }
'@ | Set-Content -LiteralPath $taskStub -Encoding utf8
    $env:NAVER_EMAIL_ADDRESS = 'offline@example.com'
    $env:NAVER_EMAIL_PASSWORD = 'dummy-mail-secret'
    $env:NAVER_EMAIL_PASSWORD_FILE = ''
    $env:CONTROL_PLANE_API_KEY = 'dummy-tunnel-secret'
    $env:PYTHONUTF8 = 'original-value'
    $env:NAVER_MCP_TEST_LOG = $taskLog
    $env:NAVER_MCP_TEST_FAIL = ''
    $taskTunnelId = 'tunnel_' + ('0' * 32)
    $taskLocation = (Get-Location).Path

    & (Join-Path $taskRoot 'scripts\start-chatgpt.ps1') -TunnelId $taskTunnelId -TunnelClient $taskStub
    $taskCalls = @(Get-Content -LiteralPath $taskLog)
    Assert-Result ($taskCalls.Count -eq 2) 'Expected doctor followed by run.'
    Assert-Result (((ConvertFrom-Json $taskCalls[0])[0]) -eq 'doctor') 'doctor must run first.'
    Assert-Result (((ConvertFrom-Json $taskCalls[1])[0]) -eq 'run') 'run must follow successful doctor.'
    $taskLogText = $taskCalls -join "`n"
    Assert-Result (-not $taskLogText.Contains('dummy-mail-secret')) 'Mail secret leaked to command arguments.'
    Assert-Result (-not $taskLogText.Contains('dummy-tunnel-secret')) 'Tunnel secret leaked to command arguments.'
    Assert-Result ($taskLogText.Contains('env:CONTROL_PLANE_API_KEY')) 'Expected an environment secret reference.'
    Assert-Result ($env:PYTHONUTF8 -eq 'original-value') 'Environment was not restored after success.'
    Assert-Result ((Get-Location).Path -eq $taskLocation) 'Working directory was not restored.'

    [IO.File]::WriteAllText($taskLog, '')
    & (Join-Path $taskRoot 'scripts\start-chatgpt.ps1') -TunnelId $taskTunnelId -TunnelClient $taskStub -CheckOnly
    Assert-Result (@(Get-Content -LiteralPath $taskLog).Count -eq 1) 'CheckOnly must not run the daemon.'

    [IO.File]::WriteAllText($taskLog, '')
    $env:NAVER_EMAIL_PASSWORD = ''
    $env:NAVER_EMAIL_PASSWORD_FILE = 'dummy-password-file'
    & (Join-Path $taskRoot 'scripts\start-chatgpt.ps1') -TunnelId $taskTunnelId -TunnelClient $taskStub -CheckOnly
    Assert-Result (@(Get-Content -LiteralPath $taskLog).Count -eq 1) 'Password file must avoid a password prompt.'
    Assert-Result (-not $env:NAVER_EMAIL_PASSWORD) 'Password file must not be copied into the environment.'
    $env:NAVER_EMAIL_PASSWORD_FILE = ''
    $env:NAVER_EMAIL_PASSWORD = 'dummy-mail-secret'

    [IO.File]::WriteAllText($taskLog, '')
    $env:NAVER_MCP_TEST_FAIL = '1'
    $taskFailed = $false
    try {
        & (Join-Path $taskRoot 'scripts\start-chatgpt.ps1') -TunnelId $taskTunnelId -TunnelClient $taskStub
    }
    catch { $taskFailed = $true }
    Assert-Result $taskFailed 'Failed doctor must stop the launcher.'
    Assert-Result (@(Get-Content -LiteralPath $taskLog).Count -eq 1) 'Failed doctor must not run the daemon.'
    Assert-Result ($env:PYTHONUTF8 -eq 'original-value') 'Environment was not restored after failure.'
    Write-Output 'Launcher assertions passed; no network or real credentials used.'
}
finally {
    foreach ($taskName in $taskNames) { [Environment]::SetEnvironmentVariable($taskName, $taskSaved[$taskName], 'Process') }
    foreach ($taskFile in @($taskStub, $taskLog)) {
        if (Test-Path -LiteralPath $taskFile) { Remove-Item -LiteralPath $taskFile -Force }
    }
    Remove-Item -LiteralPath $taskTemp -Force
}
