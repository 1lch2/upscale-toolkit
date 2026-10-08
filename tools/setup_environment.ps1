[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$Venv = '.venv',
    [ValidateSet('cpu', 'cu130')][string]$Runtime = 'cu130'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $Venv))
if (-not $venvPath.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw '构建环境必须位于项目目录内'
}
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
& $Python -m venv $venvPath
if ($LASTEXITCODE -ne 0) { throw '创建构建环境失败' }
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$torchIndex = "https://download.pytorch.org/whl/$Runtime"
# Install Torch first so the common dependency resolver doesn't choose another runtime.
& $venvPython -m pip install --disable-pip-version-check --force-reinstall --no-deps --index-url $torchIndex -r (Join-Path $projectRoot 'requirements-torch.txt')
if ($LASTEXITCODE -ne 0) { throw '安装 Torch 运行库失败' }
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw '安装公共依赖失败' }
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw '依赖一致性检查失败' }
Write-Output "构建解释器：$venvPython"
