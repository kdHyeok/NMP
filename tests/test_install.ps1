$ErrorActionPreference = 'Stop'
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('nmp-install space''s-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $taskTemp 'scripts') -Force | Out-Null
$taskInstaller = Join-Path $taskTemp 'scripts/install.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../scripts/install.ps1') -Destination $taskInstaller
$global:taskInstallCalls = [Collections.Generic.List[string]]::new()
$global:taskInstallFail = $false
function global:uv {
    $global:taskInstallCalls.Add((ConvertTo-Json -InputObject @($args) -Compress))
    $global:LASTEXITCODE = if ($global:taskInstallFail) { 9 } else { 0 }
}
try {
    $taskLocation = (Get-Location).Path
    & $taskInstaller -Mode local
    if ($global:taskInstallCalls.Count -ne 3) { throw 'Expected sync, setup and doctor.' }
    $taskSetup = ConvertFrom-Json $global:taskInstallCalls[1]
    if ($taskSetup[-3] -ne 'setup' -or $taskSetup[-2] -ne '--mode' -or $taskSetup[-1] -ne 'local') { throw 'Installer changed the argument boundary.' }
    if ((Get-Location).Path -ne $taskLocation) { throw 'Installer did not restore location.' }
    $global:taskInstallCalls.Clear()
    $global:taskInstallFail = $true
    $taskFailed = $false
    try { & $taskInstaller -Mode tunnel } catch { $taskFailed = $true }
    if (-not $taskFailed -or $global:taskInstallCalls.Count -ne 1) { throw 'Installer continued after failed sync.' }
    if ((Get-Location).Path -ne $taskLocation) { throw 'Failed installer did not restore location.' }
    Write-Output 'Installer assertions passed without network or real credentials.'
}
finally {
    Remove-Item -LiteralPath Function:\uv -Force
    Remove-Item -LiteralPath $taskInstaller -Force
    Remove-Item -LiteralPath (Join-Path $taskTemp 'scripts') -Force
    Remove-Item -LiteralPath $taskTemp -Force
    Remove-Variable -Name taskInstallCalls,taskInstallFail -Scope Global
}