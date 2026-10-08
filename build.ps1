[CmdletBinding()]
param(
    [string]$Python = '',
    [ValidateSet('auto', 'cpu', 'cu130')][string]$Runtime = 'auto',
    [switch]$IncludeModels,
    [switch]$Release,
    [switch]$Verify,
    [string]$TestModelDir = '',
    [string]$Tag = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$nativeArgs = @('-B', (Join-Path $projectRoot 'tools\build_release.py'), '--runtime', $Runtime)
if ($IncludeModels) { $nativeArgs += '--include-models' }
if ($Release) { $nativeArgs += '--release' }
if ($Verify) { $nativeArgs += '--verify' }
if ($TestModelDir) { $nativeArgs += @('--test-model-dir', $TestModelDir) }
if ($Tag) { $nativeArgs += @('--tag', $Tag) }
Push-Location -LiteralPath $projectRoot
try {
    & $Python @nativeArgs
    if ($LASTEXITCODE -ne 0) { throw '构建或验收失败，请查看上面的错误' }
} finally {
    Pop-Location
}
