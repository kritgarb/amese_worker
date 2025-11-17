@echo off
chcp 65001 >nul
REM Script para instalar o db_api como serviço do Windows
REM Usa NSSM (Non-Sucking Service Manager) - será baixado automaticamente

cls
echo.
echo ================================================
echo   Instalador de Serviço - DB API Monitor
echo   ItemSol ^> Bemsoft
echo ================================================
echo.

REM Verifica se está rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador
    echo.
    echo Como executar:
    echo   1. Clique com botão direito em install_service.bat
    echo   2. Selecione "Executar como administrador"
    echo.
    pause
    exit /b 1
)

REM Define caminhos
set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "MAIN_SCRIPT=%SCRIPT_DIR%main.py"
set "SERVICE_NAME=DBAPIMonitor"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

echo [INFO] Diretório: %SCRIPT_DIR%
echo [INFO] Python: %PYTHON_PATH%
echo [INFO] Script: %MAIN_SCRIPT%
echo.

REM Verifica se Python existe
if not exist "%PYTHON_PATH%" (
    echo [ERRO] Python não encontrado em %PYTHON_PATH%
    echo.
    echo Certifique-se de que o ambiente virtual está criado:
    echo   python -m venv .venv
    echo.
    pause
    exit /b 1
)

REM Verifica se NSSM existe, se não, baixa
if not exist "%NSSM_PATH%" (
    echo [INFO] NSSM não encontrado. Baixando automaticamente...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip' -OutFile '%SCRIPT_DIR%nssm.zip'}"
    powershell -Command "& {Expand-Archive -Path '%SCRIPT_DIR%nssm.zip' -DestinationPath '%SCRIPT_DIR%nssm_temp' -Force}"
    copy "%SCRIPT_DIR%nssm_temp\nssm-2.24-101-g897c7ad\win64\nssm.exe" "%NSSM_PATH%" >nul
    rmdir /s /q "%SCRIPT_DIR%nssm_temp"
    del "%SCRIPT_DIR%nssm.zip"
    echo [OK] NSSM baixado com sucesso!
    echo.
)

REM Remove serviço existente se houver
echo [INFO] Verificando serviço existente...
sc query %SERVICE_NAME% >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Removendo serviço existente...
    "%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1
    timeout /t 2 >nul
    echo [OK] Serviço anterior removido
)

REM Instala o serviço
echo.
echo [INFO] Instalando serviço %SERVICE_NAME%...
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" "%MAIN_SCRIPT%" >nul 2>&1
echo [OK] Serviço instalado

REM Configura o serviço
echo [INFO] Configurando serviço...
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%" >nul
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "DB API Monitor - ItemSol to Bemsoft" >nul
"%NSSM_PATH%" set %SERVICE_NAME% Description "Monitora banco de dados e envia solicitações para API Bemsoft" >nul
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START >nul
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%SCRIPT_DIR%logs\service_output.log" >nul
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%SCRIPT_DIR%logs\service_error.log" >nul
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1 >nul
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateOnline 1 >nul
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760 >nul
echo [OK] Configuração aplicada

REM Cria diretório de logs se não existir
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM Inicia o serviço
echo.
echo [INFO] Iniciando serviço...
"%NSSM_PATH%" start %SERVICE_NAME% >nul 2>&1
timeout /t 2 >nul
echo [OK] Serviço iniciado

echo.
echo ================================================
echo    INSTALAÇÃO CONCLUÍDA COM SUCESSO!
echo ================================================
echo.
echo Nome do serviço:  %SERVICE_NAME%
echo Status:           Rodando em background
echo Logs:             %SCRIPT_DIR%logs\
echo.
echo ------------------------------------------------
echo COMANDOS ÚTEIS:
echo ------------------------------------------------
echo.
echo Ver status:       services.msc
echo Ver logs:         notepad logs\service_output.log
echo Parar:            nssm stop %SERVICE_NAME%
echo Iniciar:          nssm start %SERVICE_NAME%
echo Desinstalar:      Execute uninstall_service.bat
echo.
echo ================================================
echo O serviço iniciará automaticamente ao ligar o PC
echo ================================================
echo.
pause
