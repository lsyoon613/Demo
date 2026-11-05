$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$ready = Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\synthesis-install-complete')
foreach ($asset in @('.venv\Scripts\python.exe', 'models\uspto_model.onnx', 'models\uspto_filter_model.onnx', 'models\uspto_templates.csv.gz', 'models\zinc_stock.hdf5', 'price_db\catalog.sqlite', 'price_db\enamine_inchikeys.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $asset))) { $ready = $false }
}
if (-not $ready) {
    Write-Host 'First run: installing Python dependencies, models and the local Enamine catalog.'
    Write-Host 'This can take several minutes. Keep this window open; internet access is required.'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Automatic installation failed. See the error above. Double-click start.bat to retry.' }
}
Write-Host 'Starting your local server. The browser opens automatically. Keep this window open.'
$env:STREAMLIT_BROWSER_SERVER_ADDRESS = '127.0.0.1'
& $python -m streamlit run "$PSScriptRoot\src\app.py" --server.address 127.0.0.1 --server.port 8502 --server.headless false
if ($LASTEXITCODE -ne 0) { throw 'App failed to start. Check the error above (including whether port 8502 is already in use).' }
