@echo off
REM Open an MSYS2 UCRT64 shell with gcc / make / ispc ready.
REM Usage: run notes\tools\msys2-shell.cmd from the repository root.
setlocal

set "CS149_ENV=<TOOLCHAIN_ROOT>"
set "MSYSTEM=UCRT64"
set "PATH=%CS149_ENV%\ispc-1.28.1\bin;%PATH%"

if not exist "%CS149_ENV%\msys64\msys2_shell.cmd" (
    echo [error] cannot find %CS149_ENV%\msys64\msys2_shell.cmd
    echo         expected the toolchain at <TOOLCHAIN_ROOT>, see notes\environment.md
    exit /b 1
)

call "%CS149_ENV%\msys64\msys2_shell.cmd" -defterm -here -ucrt64 %*
