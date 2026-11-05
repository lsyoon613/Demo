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
    throw 'Python 3.11 not found. Install 64-bit Python 3.11 or set SYNTHESIS_PYTHON311 to its python.exe path.'
}
Write-Output "Using Python 3.11: $python311 $($arguments -join ' ')"
& $python311 @arguments -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment creation failed' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'App dependencies failed to install' }
& $python -X utf8 setup_models.py
if ($LASTEXITCODE -ne 0) { throw 'Public model download/checksum verification failed' }
& $python -X utf8 doctor.py
Write-Output 'Core installation complete. Launch start.bat and visit http://localhost:8502.'
Write-Output 'Optional AMES: .\.venv\Scripts\python.exe -m venv .admet-venv; .\.admet-venv\Scripts\python.exe -m pip install -r requirements-admet.txt'
Write-Output 'Optional ASKCOS backend and Enamine SDF catalog: follow README.md.'
