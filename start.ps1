$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment missing. Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1'
}
& $python -m streamlit run "$PSScriptRoot\src\app.py" --server.address localhost --server.port 8502
