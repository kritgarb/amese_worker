@echo off
REM Script para gerar executavel do Bemsoft Monitor

echo ===================================
echo   BUILD BEMSOFT MONITOR EXECUTAVEL
echo ===================================
echo.

REM Ativa o ambiente virtual se existir
if exist ".venv\Scripts\activate.bat" (
    echo Ativando ambiente virtual...
    call .venv\Scripts\activate.bat
) else (
    echo AVISO: Ambiente virtual nao encontrado em .venv
    echo Usando Python do sistema...
)

echo.
echo Verificando/instalando PyInstaller...
pip install pyinstaller --quiet

echo.
echo Limpando builds anteriores...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

echo.
echo Gerando executavel com PyInstaller...
echo (Isso pode demorar alguns minutos...)
pyinstaller bemsoft_monitor.spec --clean

echo.
if exist "dist\BemsoftMonitor.exe" (
    echo ===================================
    echo   BUILD CONCLUIDO COM SUCESSO!
    echo ===================================
    echo.
    echo Executavel gerado: dist\BemsoftMonitor.exe
    echo.
    echo Proximos passos:
    echo 1. Copie o arquivo dist\BemsoftMonitor.exe para o servidor
    echo 2. Copie o arquivo .env configurado para a mesma pasta
    echo 3. Execute install_service.bat para instalar como servico
    echo.
) else (
    echo ===================================
    echo   ERRO NO BUILD!
    echo ===================================
    echo Verifique os logs acima para detalhes.
    echo.
)

pause
