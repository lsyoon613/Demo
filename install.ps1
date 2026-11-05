$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$python311 = $null
$arguments = @()
$candidates = @()
if ($env:SYNTHESIS_PYTHON311) { $candidates += @{ Program = $env:SYNTHESIS_PYTHON311; Prefix = @() } }
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += @{ Program = 'py'; Prefix = @('-3.11') }
    $candidates += @{ Program = 'py'; Prefix = @('-V:Astral/CPython3.11') }
}
if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += @{ Program = 'python'; Prefix = @() } }
foreach ($candidate in $candidates) {
    $candidateArgs = @($candidate.Prefix)
    $ErrorActionPreference = 'Continue'
    try {
        $version = & $candidate.Program @candidateArgs -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>$null
        $candidateExit = $LASTEXITCODE
    } catch {
        $version = $null
        $candidateExit = 1
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    if ($candidateExit -eq 0 -and $version -eq '3 11') {
        $python311 = $candidate.Program
        $arguments = @($candidate.Prefix)
        break
    }
}
if (-not $python311) {
    Write-Host 'Python 3.11 is missing. Installing the official Python package using Windows Package Manager...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Windows Package Manager (winget) is unavailable. Install Python 3.11 from python.org, then double-click start.bat again.'
    }
    & winget install --id Python.Python.3.11 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed. Install Python 3.11 from python.org, then double-click start.bat again.' }
    $installed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
    if (-not (Test-Path -LiteralPath $installed)) {
        throw 'Python was installed but could not be located. Close this window and double-click start.bat again.'
    }
    $python311 = $installed
    $arguments = @()
}
Write-Output "Using Python 3.11: $python311 $($arguments -join ' ')"
& $python311 @arguments -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment creation failed' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -X utf8 setup_catalog.py
if ($LASTEXITCODE -ne 0) { throw 'Bundled Enamine catalog restore/check failed' }
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'App dependencies failed to install' }
& $python -X utf8 setup_models.py
if ($LASTEXITCODE -ne 0) { throw 'Public model download/checksum verification failed' }
& $python -X utf8 doctor.py
if ($LASTEXITCODE -ne 0) { throw 'Installation diagnostics failed' }
& $python -c 'import streamlit, rdkit, aizynthfinder, pyarrow'
if ($LASTEXITCODE -ne 0) { throw 'Installed dependencies could not be imported' }
Set-Content -LiteralPath (Join-Path $PSScriptRoot '.venv\synthesis-install-complete') -Value 'local-catalog-v1' -Encoding Ascii
Write-Output 'Core installation complete. Launch start.bat and visit http://localhost:8502.'
Write-Output 'Optional AMES: .\.venv\Scripts\python.exe -m venv .admet-venv; .\.admet-venv\Scripts\python.exe -m pip install -r requirements-admet.txt'
Write-Output 'Optional ASKCOS backend: follow README.md. Enamine catalog is already installed locally.'
