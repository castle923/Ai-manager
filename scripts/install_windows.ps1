[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Wheel,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$WheelSha256,
    [Parameter(Mandatory=$true)][string]$Requirements,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$RequirementsSha256,
    [Parameter(Mandatory=$true)][string]$InstallDirectory,
    [Parameter(Mandatory=$true)][string]$HomeDirectory,
    [Parameter(Mandatory=$true)][string]$PythonExecutable
)
$ErrorActionPreference = 'Stop'
if (-not [IO.Path]::IsPathRooted($InstallDirectory) -or -not [IO.Path]::IsPathRooted($HomeDirectory)) { throw 'Use absolute install and home paths.' }
$installRoot = [IO.Path]::GetFullPath($InstallDirectory)
$appHome = [IO.Path]::GetFullPath($HomeDirectory)
function Assert-NoReparseAncestor([string]$Path) {
    $cursor = $Path
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $entry = Get-Item -LiteralPath $cursor -Force
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse paths are not supported.' }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($parent) { $parent.FullName } else { $null }
    }
}
Assert-NoReparseAncestor $installRoot
Assert-NoReparseAncestor $appHome
$installPrefix = $installRoot.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
$homePrefix = $appHome.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if ($installRoot.Equals($appHome,[StringComparison]::OrdinalIgnoreCase) -or $appHome.StartsWith($installPrefix,[StringComparison]::OrdinalIgnoreCase) -or $installRoot.StartsWith($homePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Install and app home directories must be separate.' }
if (Test-Path -LiteralPath $installRoot) { throw 'Existing install directory preserved; choose a new directory.' }
if (Test-Path -LiteralPath $appHome) { throw 'Existing app home preserved; choose a new empty home path.' }
if ((Get-FileHash -LiteralPath $Wheel -Algorithm SHA256).Hash -ne $WheelSha256) { throw 'Wheel hash mismatch.' }
if ((Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash -ne $RequirementsSha256) { throw 'Dependency lock hash mismatch.' }
& $PythonExecutable -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
& $PythonExecutable -c 'import sys,zipfile,email; z=zipfile.ZipFile(sys.argv[1]); m=[n for n in z.namelist() if n.endswith(".dist-info/METADATA")]; assert len(m)==1; d=email.message_from_bytes(z.read(m[0])); assert d["Name"]=="ai-manager-local" and d["Version"]=="0.6.0", "Unexpected wheel identity"' $Wheel
if ($LASTEXITCODE -ne 0) { throw 'Application wheel identity check failed.' }
New-Item -ItemType Directory -Path $installRoot | Out-Null
# Never remove partial installations: failure evidence stays in this new directory.
& $PythonExecutable -m venv (Join-Path $installRoot 'venv')
if ($LASTEXITCODE -ne 0) { throw 'New virtual environment creation failed.' }
$appPython = Join-Path $installRoot 'venv/Scripts/python.exe'
& $appPython -m pip install --disable-pip-version-check -r $Requirements
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed; partial install preserved.' }
& $appPython -m pip install --disable-pip-version-check --no-deps $Wheel
if ($LASTEXITCODE -ne 0) { throw 'Application wheel installation failed; partial install preserved.' }
& $appPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency validation failed.' }
$manifest = @{schema_version=1; app_home=$appHome; python=$appPython; wheel_sha256=$WheelSha256; requirements_sha256=$RequirementsSha256; credentials_copied=$false}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installRoot 'installation.json') -Encoding utf8
@'
param([int]$Port=0,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'installation.json') -Raw | ConvertFrom-Json
$arguments=@('-m','ai_manager.cli','--home',$config.app_home,'serve','--port',"$Port")
if ($NoBrowser) { $arguments += '--no-browser' }
& $config.python @arguments
exit $LASTEXITCODE
'@ | Set-Content -LiteralPath (Join-Path $installRoot 'Start-AiManager.ps1') -Encoding utf8
@'
import json
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parent
settings = json.loads((root / 'installation.json').read_text(encoding='utf-8-sig'))
raise SystemExit(subprocess.run([sys.executable, '-m', 'ai_manager.cli', '--home', settings['app_home'], 'serve', *sys.argv[1:]]).returncode)
'@ | Set-Content -LiteralPath (Join-Path $installRoot 'start_launcher.py') -Encoding utf8
@'
@echo off
setlocal DisableDelayedExpansion
"%~dp0venv\Scripts\python.exe" "%~dp0start_launcher.py" %*
exit /b %ERRORLEVEL%
'@ | Set-Content -LiteralPath (Join-Path $installRoot 'Start-AiManager.cmd') -Encoding ascii
@{status='installed';python_version='3.10';application='ai-manager-local';credentials_copied=$false;home_initialized=$false} | ConvertTo-Json
