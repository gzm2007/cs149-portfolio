# CS149 local toolchain environment (PowerShell)
#
# Usage from the repository root (note the leading dot and space):
#     . .\notes\tools\env.ps1
#
# If you get "running scripts is disabled on this system", allow scripts for
# the current window only (does not change any system setting):
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# If you would rather not touch PowerShell execution policy, use
# notes\tools\cmd.cmd or notes\tools\msys2-shell.cmd instead.

$cs149Root = '<TOOLCHAIN_ROOT>'

$cs149Paths = @(
    (Join-Path $cs149Root 'msys64\ucrt64\bin'),   # g++ / gcc / binutils
    (Join-Path $cs149Root 'msys64\usr\bin'),      # make / bash / coreutils
    (Join-Path $cs149Root 'ispc-1.28.1\bin')      # ispc.exe
)

foreach ($p in $cs149Paths) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Warning "missing directory: $p"
        continue
    }
    if (($env:Path -split ';') -notcontains $p) {
        $env:Path = "$p;$env:Path"
    }
}

# Make MSYS2's make use the UCRT64 toolchain
$env:MSYSTEM = 'UCRT64'

$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    Write-Host "python venv: $venvPython"
} else {
    Write-Host "note: no .venv here yet (prog6 plot.py needs numpy/matplotlib/scikit-learn)"
}

$gccLine = (g++ --version | Select-Object -First 1)
$makeLine = (make --version | Select-Object -First 1)
$ispcLine = (ispc --version | Select-String -SimpleMatch 'ISPC' | Select-Object -First 1)
Write-Host "g++  : $gccLine"
Write-Host "make : $makeLine"
Write-Host "ispc : $ispcLine"
