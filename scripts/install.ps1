[CmdletBinding()]
param([ValidateSet('local', 'tunnel')][string]$Mode = 'local')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Get-Command uv -ErrorAction Stop | Out-Null
Push-Location -LiteralPath $taskRoot
try {
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & uv run --frozen python -B -m naver_mail_mcp.cli setup --mode $Mode
    if ($LASTEXITCODE -ne 0) { throw 'NMP setup failed. Existing configuration was preserved.' }
    & uv run --frozen python -B -m naver_mail_mcp.cli doctor
    if ($LASTEXITCODE -ne 0) { throw 'NMP local verification failed.' }
    if ($Mode -eq 'tunnel') { Write-Output 'Run: uv run --frozen nmp tunnel' }
    else { Write-Output 'Import .nmp/mcp.json into your local MCP client.' }
}
finally { Pop-Location }