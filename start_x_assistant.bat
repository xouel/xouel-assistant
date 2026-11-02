@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   X-ASSISTANT - INICIALIZADOR UNIFICADO (WINDOWS 11)
echo ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [*] Build de producao do front-end nao encontrado. Compilando agora...
    pushd frontend
    call npm run build
    popd
)

if "%~1"=="--silent" (
    echo [*] Iniciando em segundo plano sem janela de console...
    start "" ".venv\Scripts\pythonw.exe" "scripts\launcher.pyw"
    exit /b 0
)

echo [*] Iniciando X-Assistant...
echo [*] Atalhos de foco: Ctrl + Alt + X  ou  Ctrl + Shift + X
echo [*] Pressione Ctrl + C para encerrar o assistente.
echo.
".venv\Scripts\python.exe" "scripts\launcher.pyw"
