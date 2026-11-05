$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or the Windows py launcher is missing' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'App dependencies failed to install' }
& $python -X utf8 setup_models.py
if ($LASTEXITCODE -ne 0) { throw 'Public model download/checksum verification failed' }
& $python -X utf8 doctor.py
Write-Output 'Core installation complete. Launch start.bat and visit http://localhost:8502.'
Write-Output 'Optional AMES: py -3.11 -m venv .admet-venv; .\.admet-venv\Scripts\python.exe -m pip install -r requirements-admet.txt'
Write-Output 'Optional ASKCOS backend and Enamine SDF catalog: follow README.md.'
