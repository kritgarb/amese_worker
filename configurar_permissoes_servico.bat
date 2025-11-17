@echo off
chcp 65001 >nul
cls
echo.
echo ================================================
echo   Configurar Permissões do Serviço
echo ================================================
echo.

REM Verifica se está rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador
    pause
    exit /b 1
)

set "SERVICE_NAME=DBAPIMonitor"
set "NSSM_PATH=%~dp0nssm.exe"

echo PROBLEMA IDENTIFICADO:
echo ----------------------
echo O serviço está configurado para rodar como "Local System"
echo que pode não ter permissões para:
echo   - Acessar SQL Server na rede
echo   - Ler variáveis de ambiente
echo   - Acessar APIs externas
echo.
echo SOLUÇÕES POSSÍVEIS:
echo.
echo [1] Rodar como conta de usuário atual (RECOMENDADO)
echo     - Tem acesso ao SQL Server
echo     - Lê .env corretamente
echo     - Precisa de senha
echo.
echo [2] Rodar como Local System com TrustServerCertificate
echo     - Pode ter limitações de rede
echo     - Melhor para testes
echo.
echo [3] Apenas verificar configuração atual
echo.
choice /C 123 /M "Escolha uma opção"

if errorlevel 3 goto :verificar
if errorlevel 2 goto :localsystem
if errorlevel 1 goto :usuario

:usuario
echo.
echo ================================================
echo   Configurando para rodar como Usuário
echo ================================================
echo.
echo Digite o nome do usuário (ex: Administrator ou DOMINIO\Usuario):
set /p USERNAME_INPUT=

echo.
echo Digite a senha do usuário:
set /p PASSWORD_INPUT=

echo.
echo [INFO] Parando serviço...
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 >nul

echo [INFO] Configurando conta de usuário...
"%NSSM_PATH%" set %SERVICE_NAME% ObjectName "%USERNAME_INPUT%" "%PASSWORD_INPUT%"

if %errorLevel% equ 0 (
    echo [OK] Conta configurada com sucesso!
) else (
    echo [ERRO] Falha ao configurar conta
    echo        Verifique se usuário e senha estão corretos
    pause
    exit /b 1
)

echo.
echo [INFO] Iniciando serviço...
"%NSSM_PATH%" start %SERVICE_NAME%
timeout /t 3 >nul

sc.exe query %SERVICE_NAME% | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo [OK] Serviço INICIADO COM SUCESSO!
) else (
    echo [ERRO] Serviço ainda não está rodando
    sc.exe query %SERVICE_NAME%
)
goto :fim

:localsystem
echo.
echo ================================================
echo   Mantendo Local System
echo ================================================
echo.
echo [INFO] Verificando configuração atual...
"%NSSM_PATH%" get %SERVICE_NAME% ObjectName

echo.
echo [INFO] O serviço continuará rodando como Local System
echo.
echo Certifique-se de que:
echo   1. SQL Server aceita conexões do sistema local
echo   2. Firewall permite acesso
echo   3. TrustServerCertificate está habilitado na connection string
echo.
pause
goto :fim

:verificar
echo.
echo ================================================
echo   Configuração Atual
echo ================================================
echo.
echo [INFO] Conta que executa o serviço:
"%NSSM_PATH%" get %SERVICE_NAME% ObjectName
echo.
echo [INFO] Configuração completa:
"%NSSM_PATH%" dump %SERVICE_NAME%
echo.
pause
goto :fim

:fim
echo.
echo ================================================
echo.
pause
