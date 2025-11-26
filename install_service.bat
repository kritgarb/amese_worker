@echo off
REM Script para instalar o Bemsoft Monitor como servico Windows
REM Requer NSSM (Non-Sucking Service Manager)

setlocal enabledelayedexpansion

echo ===================================
echo   INSTALADOR SERVICO WINDOWS
echo   Bemsoft Monitor
echo ===================================
echo.

REM Verifica se esta rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERRO: Este script precisa ser executado como Administrador!
    echo Clique com botao direito e selecione "Executar como Administrador"
    echo.
    pause
    exit /b 1
)

REM Define variaveis
set SERVICE_NAME=BemsoftMonitor
set EXE_PATH=%~dp0BemsoftMonitor.exe
set NSSM_PATH=%~dp0nssm.exe
set WORK_DIR=%~dp0

REM Verifica se o executavel existe
if not exist "%EXE_PATH%" (
    echo ERRO: Executavel nao encontrado: %EXE_PATH%
    echo.
    echo Execute primeiro o build.bat para gerar o executavel
    echo ou copie o BemsoftMonitor.exe para esta pasta.
    echo.
    pause
    exit /b 1
)

REM Verifica se o .env existe
if not exist "%WORK_DIR%.env" (
    echo AVISO: Arquivo .env nao encontrado!
    echo.
    echo O servico precisa do arquivo .env configurado na mesma pasta.
    echo Copie e configure o arquivo .env antes de continuar.
    echo.
    set /p continue="Deseja continuar mesmo assim? (S/N): "
    if /i "!continue!" neq "S" (
        exit /b 0
    )
)

REM Verifica se o NSSM esta disponivel
set NSSM_CMD=nssm
where nssm >nul 2>&1
if %errorLevel% neq 0 (
    if exist "%NSSM_PATH%" (
        set NSSM_CMD=%NSSM_PATH%
        echo NSSM encontrado localmente: %NSSM_PATH%
    ) else (
        echo.
        echo ERRO: NSSM nao encontrado!
        echo.
        echo O NSSM (Non-Sucking Service Manager) e necessario para instalar servicos.
        echo.
        echo Opcoes:
        echo 1. Baixe o NSSM de: https://nssm.cc/download
        echo 2. Extraia o nssm.exe (win64/nssm.exe) para esta pasta
        echo 3. Execute este script novamente
        echo.
        echo OU instale globalmente:
        echo - Com Chocolatey: choco install nssm
        echo.
        pause
        exit /b 1
    )
) else (
    echo NSSM encontrado no PATH do sistema
)

echo.
echo Verificando se o servico ja existe...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo O servico "%SERVICE_NAME%" ja existe!
    echo.
    set /p reinstall="Deseja remover e reinstalar? (S/N): "
    if /i "!reinstall!"=="S" (
        echo Parando servico...
        %NSSM_CMD% stop "%SERVICE_NAME%" >nul 2>&1
        timeout /t 2 /nobreak >nul
        echo Removendo servico...
        %NSSM_CMD% remove "%SERVICE_NAME%" confirm
        timeout /t 2 /nobreak >nul
    ) else (
        echo Instalacao cancelada.
        pause
        exit /b 0
    )
)

echo.
echo Instalando servico...
%NSSM_CMD% install "%SERVICE_NAME%" "%EXE_PATH%"

echo Configurando servico...
%NSSM_CMD% set "%SERVICE_NAME%" AppDirectory "%WORK_DIR%"
%NSSM_CMD% set "%SERVICE_NAME%" DisplayName "Bemsoft Monitor - SQL to API"
%NSSM_CMD% set "%SERVICE_NAME%" Description "Monitora SQL Server e envia dados para API Bemsoft"
%NSSM_CMD% set "%SERVICE_NAME%" Start SERVICE_AUTO_START
%NSSM_CMD% set "%SERVICE_NAME%" AppStdout "%WORK_DIR%logs\service_output.log"
%NSSM_CMD% set "%SERVICE_NAME%" AppStderr "%WORK_DIR%logs\service_error.log"
%NSSM_CMD% set "%SERVICE_NAME%" AppRotateFiles 1
%NSSM_CMD% set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Cria pasta de logs se nao existir
if not exist "%WORK_DIR%logs" mkdir "%WORK_DIR%logs"

echo.
echo Iniciando servico...
%NSSM_CMD% start "%SERVICE_NAME%"

echo.
echo ===================================
echo   INSTALACAO CONCLUIDA!
echo ===================================
echo.
echo Servico: %SERVICE_NAME%
echo Status:
sc query "%SERVICE_NAME%" | findstr "STATE"
echo.
echo Logs do servico:
echo - Saida: %WORK_DIR%logs\service_output.log
echo - Erros: %WORK_DIR%logs\service_error.log
echo.
echo Comandos uteis:
echo - Verificar status: sc query %SERVICE_NAME%
echo - Parar servico:    sc stop %SERVICE_NAME%
echo - Iniciar servico:  sc start %SERVICE_NAME%
echo - Ver logs:         Services.msc
echo.
echo Para desinstalar, execute: uninstall_service.bat
echo.
pause
