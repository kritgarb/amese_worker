@echo off
REM Script para desinstalar o servico Bemsoft Monitor

setlocal enabledelayedexpansion

echo ===================================
echo   DESINSTALADOR SERVICO WINDOWS
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
set NSSM_PATH=%~dp0nssm.exe

REM Verifica se o NSSM esta disponivel
set NSSM_CMD=nssm
where nssm >nul 2>&1
if %errorLevel% neq 0 (
    if exist "%NSSM_PATH%" (
        set NSSM_CMD=%NSSM_PATH%
    ) else (
        echo AVISO: NSSM nao encontrado.
        echo Tentando remover servico com sc.exe...
        set NSSM_CMD=
    )
)

echo Verificando se o servico existe...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo O servico "%SERVICE_NAME%" nao esta instalado.
    echo.
    pause
    exit /b 0
)

echo.
echo Servico encontrado:
sc query "%SERVICE_NAME%" | findstr "STATE DISPLAY_NAME"
echo.

set /p confirm="Deseja realmente remover o servico? (S/N): "
if /i "!confirm!" neq "S" (
    echo Desinstalacao cancelada.
    pause
    exit /b 0
)

echo.
echo Parando servico...
if defined NSSM_CMD (
    %NSSM_CMD% stop "%SERVICE_NAME%"
) else (
    sc stop "%SERVICE_NAME%"
)
timeout /t 3 /nobreak >nul

echo.
echo Removendo servico...
if defined NSSM_CMD (
    %NSSM_CMD% remove "%SERVICE_NAME%" confirm
) else (
    sc delete "%SERVICE_NAME%"
)

echo.
REM Verifica se foi removido
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% neq 0 (
    echo ===================================
    echo   DESINSTALACAO CONCLUIDA!
    echo ===================================
    echo.
    echo O servico "%SERVICE_NAME%" foi removido com sucesso.
    echo.
    echo NOTA: Os arquivos do executavel e configuracao (.env)
    echo nao foram removidos. Voce pode remove-los manualmente se desejar.
    echo.
) else (
    echo ===================================
    echo   ERRO NA DESINSTALACAO
    echo ===================================
    echo.
    echo Nao foi possivel remover o servico completamente.
    echo Tente parar manualmente em Services.msc e execute novamente.
    echo.
)

pause
