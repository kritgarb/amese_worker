@echo off
chcp 65001 >nul
cls
echo.
echo ================================================
echo   Teste de Conexões
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_PATH%" (
    echo [ERRO] Python não encontrado em: %PYTHON_PATH%
    pause
    exit /b 1
)

"%PYTHON_PATH%" "%SCRIPT_DIR%testar_conexao.py"

echo.
pause
