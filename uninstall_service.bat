@echo off
chcp 65001 >nul
REM Script para desinstalar o serviço DB API Monitor

cls
echo.
echo ================================================
echo   Desinstalador - DB API Monitor
echo ================================================
echo.

REM Verifica se está rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador
    echo.
    echo Como executar:
    echo   1. Clique com botão direito em uninstall_service.bat
    echo   2. Selecione "Executar como administrador"
    echo.
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "SERVICE_NAME=DBAPIMonitor"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

if not exist "%NSSM_PATH%" (
    echo [ERRO] NSSM não encontrado.
    echo O serviço pode não estar instalado ou foi instalado manualmente.
    echo.
    pause
    exit /b 1
)

echo [INFO] Verificando serviço...
sc query %SERVICE_NAME% >nul 2>&1
if %errorLevel% neq 0 (
    echo [AVISO] Serviço não encontrado. Já pode ter sido removido.
    echo.
    pause
    exit /b 0
)

echo [INFO] Parando serviço...
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 >nul
echo [OK] Serviço parado

echo [INFO] Removendo serviço...
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1
echo [OK] Serviço removido

echo.
echo ================================================
echo   DESINSTALAÇÃO CONCLUÍDA COM SUCESSO!
echo ================================================
echo.
echo O serviço foi removido do sistema.
echo Para reinstalar, execute install_service.bat
echo.
pause
