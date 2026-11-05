$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$backend = Join-Path $PSScriptRoot 'backends\askcos'

function Test-AskcosReady {
    try {
        $status = Invoke-RestMethod 'http://127.0.0.1:9100/api/admin/get-backend-status' -TimeoutSec 5
        foreach ($name in @('context_quarc','forward_wldn5','impurity_predictor','fast_filter','atom_map_indigo')) {
            $module = @($status.modules | Where-Object { $_.name -eq $name -and $_.to_start -eq $true -and $_.ready -eq $true })
            if ($module.Count -ne 1) { return $false }
        }
        return $true
    } catch { return $false }
}

if (-not (Test-AskcosReady)) {
    Write-Host 'Preparing ASKCOS locally: WSL2, Ubuntu, Docker, model downloads and CPU containers.'
    Write-Host 'First setup can require many GB and a long download/build. A Windows restart may be needed for WSL.'
    $ErrorActionPreference = 'Continue'
    $distros = @(& wsl.exe --list --quiet 2>$null | ForEach-Object { ($_ -replace "`0", '').Trim() })
    $ErrorActionPreference = 'Stop'
    $distro = $env:SYNTHESIS_WSL_DISTRO
    if (-not $distro) { $distro = @($distros | Where-Object { $_ -match '^Ubuntu' } | Select-Object -First 1)[0] }
    if (-not $distro) {
        Write-Host 'Installing Ubuntu/WSL. Accept the Windows administrator prompt. After restart, double-click start.bat again.'
        $installer = Start-Process wsl.exe -ArgumentList '--install -d Ubuntu --no-launch' -Verb RunAs -Wait -PassThru
        if ($installer.ExitCode -ne 0 -and $installer.ExitCode -ne 3010) { throw 'WSL setup did not complete. Review the Windows installer output and retry start.bat.' }
        $distro = 'Ubuntu'
        & wsl.exe -d $distro -u root -- true
        if ($LASTEXITCODE -ne 0) { throw 'Restart Windows to complete WSL/Ubuntu installation, then double-click start.bat again.' }
    }
    & wsl.exe -d $distro -u root -- true
    if ($LASTEXITCODE -ne 0) { throw 'Ubuntu is not initialized. Open Ubuntu once to complete its setup, then retry start.bat.' }
    $version = & wsl.exe -d $distro -u root -- uname -r
    if ($version -notmatch 'WSL2|microsoft-standard') {
        & wsl.exe --set-version $distro 2
        if ($LASTEXITCODE -ne 0) { throw 'WSL2 conversion failed. Enable Windows virtualization and restart, then retry start.bat.' }
    }
    $linuxBackend = (& wsl.exe -d $distro -u root -- wslpath -a -u $backend).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $linuxBackend) { throw 'Cannot resolve ASKCOS directory inside WSL.' }
    & wsl.exe -d $distro -u root -- bash "$linuxBackend/install_docker.sh"
    if ($LASTEXITCODE -ne 0) { throw 'Docker/Compose installation or startup failed. Review the output above.' }
    & $python -X utf8 "$backend\prepare.py"
    if ($LASTEXITCODE -ne 0) { throw 'ASKCOS source/model download failed. Retry start.bat to resume.' }
    & wsl.exe -d $distro -u root -- docker compose -f "$linuxBackend/compose.local.yaml" --parallel 2 build
    if ($LASTEXITCODE -ne 0) { throw 'ASKCOS container build failed. Retry start.bat; completed Docker build layers are reused.' }
    & wsl.exe -d $distro -u root -- docker compose -f "$linuxBackend/compose.local.yaml" up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw 'ASKCOS container startup failed. Check whether another service occupies port 9100.' }
    # Keep WSL alive while the prediction service is in use. Reuse only our own keeper PID.
    $keeperFile = Join-Path $backend 'keeper.json'
    $keeperAlive = $false
    if (Test-Path $keeperFile) {
        $saved = Get-Content $keeperFile -Raw | ConvertFrom-Json
        $existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
        $keeperAlive = $existing -and $existing.Name -eq 'wsl.exe' -and $existing.CommandLine.Contains('sleep infinity') -and $existing.CreationDate.ToUniversalTime().ToString('o') -eq $saved.created
    }
    if (-not $keeperAlive) {
        $keeper = Start-Process wsl.exe -ArgumentList "-d $distro --exec sleep infinity" -WindowStyle Hidden -PassThru
        $info = Get-CimInstance Win32_Process -Filter "ProcessId = $($keeper.Id)"
        @{pid=$keeper.Id; created=$info.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $keeperFile -Encoding UTF8
    }
    for ($i=0; $i -lt 120; $i++) {
        if (Test-AskcosReady) { break }
        Start-Sleep -Seconds 5
    }
    if (-not (Test-AskcosReady)) { throw 'ASKCOS models are not ready. Retry start.bat after reviewing Docker logs.' }
}
Write-Host 'ASKCOS: all five required model services are ready.'

$admet = Join-Path $PSScriptRoot '.admet-venv\Scripts\python.exe'
$amesMarker = Join-Path $PSScriptRoot '.admet-venv\ames-inference-verified'
if (-not (Test-Path $amesMarker) -or -not (Test-Path $admet)) {
    Write-Host 'Preparing AMES: separate ADMET-AI environment and model warm-up.'
    & $python -m venv (Join-Path $PSScriptRoot '.admet-venv')
    if ($LASTEXITCODE -ne 0) { throw 'ADMET-AI environment creation failed' }
    & $admet -m pip install -r (Join-Path $PSScriptRoot 'requirements-admet.txt')
    if ($LASTEXITCODE -ne 0) { throw 'ADMET-AI installation failed. Retry start.bat.' }
    & $python -X utf8 (Join-Path $PSScriptRoot 'scripts\check_backends.py') ames
    if ($LASTEXITCODE -ne 0) { throw 'AMES model warm-up failed. Review model download/inference error above and retry start.bat.' }
    Set-Content -LiteralPath $amesMarker -Value 'admet-ai-2.0.1' -Encoding Ascii
}
Write-Host 'AMES: installed and inference verified. Full local app is ready to start.'
