@echo off
REM Open a cmd session with gcc / make / ispc already on PATH.
REM Unlike notes\tools\env.ps1 this entry point is not affected by the
REM PowerShell execution policy.
REM
REM Usage: run notes\tools\cmd.cmd from the repository root.
setlocal

set "CS149_ENV=<TOOLCHAIN_ROOT>"
set "MSYSTEM=UCRT64"
set "PATH=%CS149_ENV%\msys64\ucrt64\bin;%CS149_ENV%\msys64\usr\bin;%CS149_ENV%\ispc-1.28.1\bin;%PATH%"

if not exist "%CS149_ENV%\msys64\ucrt64\bin\g++.exe" (
    echo [error] cannot find %CS149_ENV%\msys64\ucrt64\bin\g++.exe
    echo         expected the toolchain at <TOOLCHAIN_ROOT>, see notes\environment.md
    exit /b 1
)

echo ================================================
echo  CS149 toolchain ready: gcc / make / ispc
echo  cwd: %CD%
echo ================================================
g++ --version | findstr /r /c:"g++"
cmd /k
