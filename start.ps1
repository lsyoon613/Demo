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
$appPath = Join-Path $PSScriptRoot 'src\app.py'
$port = 8502
while ($port -le 8522) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { break }
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process.CommandLine -and $process.CommandLine.Contains($appPath) -and $process.CommandLine.Contains('streamlit')) {
            try {
                $health = Invoke-WebRequest "http://127.0.0.1:$port/_stcore/health" -UseBasicParsing -TimeoutSec 3
                if ($health.StatusCode -eq 200 -and $health.Content.Trim() -eq 'ok') {
                    Write-Host "This app is already running. Opening http://127.0.0.1:$port"
                    Start-Process "http://127.0.0.1:$port"
                    exit 0
                }
            } catch { }
        }
    }
    $port++
}
if ($port -gt 8522) { throw 'No free local port in 8502-8522. Close an unused app server and retry.' }
Write-Host "Starting your local server at http://127.0.0.1:$port . Keep this window open."
$env:STREAMLIT_BROWSER_SERVER_ADDRESS = '127.0.0.1'
& $python -m streamlit run $appPath --server.address 127.0.0.1 --server.port $port --server.headless false
if ($LASTEXITCODE -ne 0) { throw 'App failed to start. See the error above.' }
