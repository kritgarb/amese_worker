@echo off
chcp 65001 >nul
cls
echo.
echo ================================================
echo   Diagnóstico do Serviço DBAPIMonitor
echo ================================================
echo.

REM Verifica se está rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "SERVICE_NAME=DBAPIMonitor"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

echo [1] Verificando status do serviço...
sc.exe query %SERVICE_NAME%
echo.

echo [2] Verificando configuração do NSSM...
if exist "%NSSM_PATH%" (
    echo [OK] NSSM encontrado
    "%NSSM_PATH%" dump %SERVICE_NAME%
) else (
    echo [ERRO] NSSM não encontrado em %NSSM_PATH%
)
echo.

echo [3] Verificando arquivos essenciais...
set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "MAIN_SCRIPT=%SCRIPT_DIR%main.py"

if exist "%PYTHON_PATH%" (
    echo [OK] Python encontrado: %PYTHON_PATH%
) else (
    echo [ERRO] Python não encontrado: %PYTHON_PATH%
)

if exist "%MAIN_SCRIPT%" (
    echo [OK] Script principal encontrado: %MAIN_SCRIPT%
) else (
    echo [ERRO] Script principal não encontrado: %MAIN_SCRIPT%
)
echo.

echo [4] Testando execução manual do Python...
echo Comando: "%PYTHON_PATH%" "%MAIN_SCRIPT%"
echo.
echo Pressione Ctrl+C para interromper após alguns segundos...
"%PYTHON_PATH%" "%MAIN_SCRIPT%"
echo.

echo [5] Verificando logs do Windows Event Viewer...
echo Últimas 5 entradas relacionadas ao serviço:
powershell -Command "Get-EventLog -LogName Application -Newest 5 -EntryType Error,Warning | Where-Object {$_.Source -like '*DBAPIMonitor*' -or $_.Message -like '*DBAPIMonitor*'} | Format-List TimeGenerated,EntryType,Source,Message"
echo.

echo [6] Verificando logs do serviço...
if exist "%SCRIPT_DIR%logs\service_output.log" (
    echo === service_output.log (últimas 20 linhas) ===
    powershell -Command "Get-Content '%SCRIPT_DIR%logs\service_output.log' -Tail 20 -ErrorAction SilentlyContinue"
) else (
    echo [INFO] service_output.log não existe ainda
)
echo.

if exist "%SCRIPT_DIR%logs\service_error.log" (
    echo === service_error.log (últimas 20 linhas) ===
    powershell -Command "Get-Content '%SCRIPT_DIR%logs\service_error.log' -Tail 20 -ErrorAction SilentlyContinue"
) else (
    echo [INFO] service_error.log não existe ainda
)
echo.

echo ================================================
echo   Diagnóstico completo
echo ================================================
echo.
pause
