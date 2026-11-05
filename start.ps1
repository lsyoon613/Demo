$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run "$PSScriptRoot\src\app.py" --server.address localhost --server.port 8502
