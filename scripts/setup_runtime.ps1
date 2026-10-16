# Fresh native Windows environment only; no model loading or inference.
$ErrorActionPreference = "Stop"
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'AiManager/m1-20261016/runtime'
$runtimeVenv = Join-Path $runtimeRoot 'venv'
if (Test-Path -LiteralPath $runtimeVenv) { throw 'Runtime environment already exists; preserve it and use runtime-check.' }
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
py -3.10 -m venv $runtimeVenv
if ($LASTEXITCODE) { throw 'Failed to create environment' }
$runtimePython = Join-Path $runtimeVenv 'Scripts/python.exe'
& $runtimePython -m pip install 'pip==26.2.1' --no-cache-dir
if ($LASTEXITCODE) { throw 'pip installation failed' }
& $runtimePython -m pip install 'torch==2.9.1' 'torchaudio==2.9.1' --index-url https://download.pytorch.org/whl/cu128 --no-cache-dir
if ($LASTEXITCODE) { throw 'CUDA wheel installation failed' }
& $runtimePython -m pip install -r (Join-Path $PSScriptRoot '../requirements-runtime.lock') --no-cache-dir
if ($LASTEXITCODE) { throw 'Qwen runtime installation failed' }
& $runtimePython -m pip check
if ($LASTEXITCODE) { throw 'Runtime dependencies are inconsistent' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../requirements-runtime.lock') -Destination (Join-Path $runtimeRoot 'requirements.lock')
Write-Output 'Run ai-manager runtime-check in the app environment; this setup did not load a model.'
