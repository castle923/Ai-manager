# Fresh native Windows environment only; no model loading or inference.
param([Parameter(Mandatory=$true)][string]$HomeDirectory,[Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference = "Stop"
if (-not [IO.Path]::IsPathRooted($HomeDirectory)) { throw 'Use an absolute app home.' }
$runtimeRoot = Join-Path ([IO.Path]::GetFullPath($HomeDirectory)) 'runtime'
$cursor = $runtimeRoot
while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse runtime paths are not supported.' }
    }
    $parent = [IO.Directory]::GetParent($cursor)
    $cursor = if ($parent) { $parent.FullName } else { $null }
}
$runtimeVenv = Join-Path $runtimeRoot 'venv'
if (Test-Path -LiteralPath $runtimeVenv) { throw 'Runtime environment already exists; preserve it and use runtime-check.' }
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
& $PythonExecutable -m venv $runtimeVenv
if ($LASTEXITCODE) { throw 'Failed to create environment' }
$runtimePython = Join-Path $runtimeVenv 'Scripts/python.exe'
& $runtimePython -m pip install 'pip==26.2.1'
if ($LASTEXITCODE) { throw 'pip installation failed' }
& $runtimePython -m pip install 'torch==2.9.1' 'torchaudio==2.9.1' --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE) { throw 'CUDA wheel installation failed' }
& $runtimePython -m pip install -r (Join-Path $PSScriptRoot '../requirements-runtime.lock')
if ($LASTEXITCODE) { throw 'Qwen runtime installation failed' }
& $runtimePython -m pip check
if ($LASTEXITCODE) { throw 'Runtime dependencies are inconsistent' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../requirements-runtime.lock') -Destination (Join-Path $runtimeRoot 'requirements.lock')
Write-Output 'Run ai-manager --home <same home> runtime-check in the app environment; this setup did not load a model.'
