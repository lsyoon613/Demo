$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment missing. Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1'
}
Write-Host 'Open http://127.0.0.1:8502 in your browser. Keep this window open.'
$env:STREAMLIT_BROWSER_SERVER_ADDRESS = '127.0.0.1'
& $python -m streamlit run "$PSScriptRoot\src\app.py" --server.address 127.0.0.1 --server.port 8502 --server.headless false
if ($LASTEXITCODE -ne 0) { throw 'App failed to start. Check the error above (including whether port 8502 is already in use).' }
