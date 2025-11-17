@echo off
chcp 65001 >nul
cls
echo.
echo ================================================
echo   Instalador MELHORADO - DB API Monitor
echo   ItemSol ^> Bemsoft
echo ================================================
echo.

REM Verifica se está rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador
    echo.
    echo Como executar:
    echo   1. Clique com botão direito em instalar_servico_v2.bat
    echo   2. Selecione "Executar como administrador"
    echo.
    pause
    exit /b 1
)

REM Define caminhos - usa o diretório atual
set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "MAIN_SCRIPT=%SCRIPT_DIR%main.py"
set "SERVICE_NAME=DBAPIMonitor"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

echo [INFO] Diretório de instalação: %SCRIPT_DIR%
echo.

REM ============================================
REM FASE 1: VERIFICAÇÃO DE PRÉ-REQUISITOS
REM ============================================
echo [FASE 1] Verificando pré-requisitos...
echo.

echo [1.1] Verificando Python...
if not exist "%PYTHON_PATH%" (
    echo [ERRO] Python não encontrado em:
    echo        %PYTHON_PATH%
    echo.
    echo Certifique-se de que o ambiente virtual está criado:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo [OK] Python encontrado

echo [1.2] Verificando script principal...
if not exist "%MAIN_SCRIPT%" (
    echo [ERRO] Script principal não encontrado em:
    echo        %MAIN_SCRIPT%
    echo.
    pause
    exit /b 1
)
echo [OK] Script principal encontrado

echo [1.3] Verificando arquivo .env...
if not exist "%SCRIPT_DIR%.env" (
    echo [AVISO] Arquivo .env não encontrado!
    echo         O script pode não funcionar corretamente sem configurações.
    echo.
    choice /C SN /M "Deseja continuar mesmo assim? (S=Sim, N=Não)"
    if errorlevel 2 exit /b 1
) else (
    echo [OK] Arquivo .env encontrado
)

echo [1.4] Criando diretórios necessários...
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"
if not exist "%SCRIPT_DIR%completo" mkdir "%SCRIPT_DIR%completo"
if not exist "%SCRIPT_DIR%completo\failed_events" mkdir "%SCRIPT_DIR%completo\failed_events"
echo [OK] Diretórios criados

echo.
echo [1.5] Testando execução do Python (5 segundos)...
echo       Pressione Ctrl+C se aparecer erros...
echo.
start /B "" "%PYTHON_PATH%" "%MAIN_SCRIPT%" > "%SCRIPT_DIR%logs\test_startup.log" 2>&1
timeout /t 5 >nul

REM Verifica se o processo ainda está rodando
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "python.exe" >nul
if %errorLevel% equ 0 (
    echo [OK] Script está rodando corretamente!
    echo      Parando teste...
    taskkill /F /IM python.exe >nul 2>&1
) else (
    echo [ERRO] Script não iniciou corretamente!
    echo        Verifique o log em: %SCRIPT_DIR%logs\test_startup.log
    echo.
    type "%SCRIPT_DIR%logs\test_startup.log"
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Todos os pré-requisitos atendidos!
echo.

REM ============================================
REM FASE 2: DOWNLOAD E CONFIGURAÇÃO DO NSSM
REM ============================================
echo [FASE 2] Configurando NSSM...
echo.

if not exist "%NSSM_PATH%" (
    echo [2.1] NSSM não encontrado. Baixando automaticamente...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip' -OutFile '%SCRIPT_DIR%nssm.zip'}"

    if not exist "%SCRIPT_DIR%nssm.zip" (
        echo [ERRO] Falha ao baixar NSSM!
        echo        Baixe manualmente de: https://nssm.cc/download
        echo        E coloque nssm.exe na pasta: %SCRIPT_DIR%
        pause
        exit /b 1
    )

    echo [2.2] Extraindo NSSM...
    powershell -Command "& {Expand-Archive -Path '%SCRIPT_DIR%nssm.zip' -DestinationPath '%SCRIPT_DIR%nssm_temp' -Force}"
    copy "%SCRIPT_DIR%nssm_temp\nssm-2.24-101-g897c7ad\win64\nssm.exe" "%NSSM_PATH%" >nul
    rmdir /s /q "%SCRIPT_DIR%nssm_temp"
    del "%SCRIPT_DIR%nssm.zip"
    echo [OK] NSSM baixado e extraído com sucesso!
) else (
    echo [OK] NSSM já existe
)
echo.

REM ============================================
REM FASE 3: INSTALAÇÃO DO SERVIÇO
REM ============================================
echo [FASE 3] Instalando serviço...
echo.

echo [3.1] Removendo serviço existente (se houver)...
sc.exe query %SERVICE_NAME% >nul 2>&1
if %errorLevel% equ 0 (
    sc.exe stop %SERVICE_NAME% >nul 2>&1
    timeout /t 2 >nul
    sc.exe delete %SERVICE_NAME% >nul 2>&1
    timeout /t 2 >nul
    echo [OK] Serviço anterior removido
) else (
    echo [INFO] Nenhum serviço anterior encontrado
)

echo [3.2] Instalando novo serviço...
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" "%MAIN_SCRIPT%"
if %errorLevel% neq 0 (
    echo [ERRO] Falha ao instalar serviço!
    pause
    exit /b 1
)
echo [OK] Serviço instalado

echo [3.3] Configurando serviço...
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "DB API Monitor - ItemSol to Bemsoft"
"%NSSM_PATH%" set %SERVICE_NAME% Description "Monitora banco de dados e envia solicitações para API Bemsoft"
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%SCRIPT_DIR%logs\service_output.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%SCRIPT_DIR%logs\service_error.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateOnline 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760

REM Define comportamento de recuperação em caso de falha
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 5000

echo [OK] Configuração aplicada

echo.
echo [3.4] Iniciando serviço...
"%NSSM_PATH%" start %SERVICE_NAME%
timeout /t 3 >nul

REM Verifica se iniciou
sc.exe query %SERVICE_NAME% | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo [OK] Serviço iniciado com SUCESSO!
) else (
    echo [ERRO] Serviço instalado mas não está rodando!
    echo.
    echo Verificando status...
    sc.exe query %SERVICE_NAME%
    echo.
    echo Verificando logs...
    if exist "%SCRIPT_DIR%logs\service_error.log" (
        echo === Últimas linhas do log de erro ===
        powershell -Command "Get-Content '%SCRIPT_DIR%logs\service_error.log' -Tail 10 -ErrorAction SilentlyContinue"
    )
    echo.
    echo Execute diagnosticar_servico.bat para mais informações
)

echo.
echo ================================================
echo    INSTALAÇÃO CONCLUÍDA!
echo ================================================
echo.
echo Local:     %SCRIPT_DIR%
echo Logs:      %SCRIPT_DIR%logs\
echo Python:    %PYTHON_PATH%
echo Script:    %MAIN_SCRIPT%
echo.
echo Comandos úteis:
echo   Ver status:    sc.exe query %SERVICE_NAME%
echo   Ver logs:      notepad "%SCRIPT_DIR%logs\service_output.log"
echo   Parar:         nssm stop %SERVICE_NAME%
echo   Iniciar:       nssm start %SERVICE_NAME%
echo   Reiniciar:     nssm restart %SERVICE_NAME%
echo   Desinstalar:   uninstall_service.bat
echo   Diagnóstico:   diagnosticar_servico.bat
echo.
pause
