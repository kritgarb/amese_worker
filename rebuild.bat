@echo off
echo ========================================
echo Reconstruindo executavel com PyInstaller
echo ========================================
echo.

REM Remove build e dist antigos
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Compila o executavel
pyinstaller main.spec

REM Copia o .env para o diretorio dist
if exist .env (
    echo.
    echo Copiando .env para dist\...
    copy .env dist\
    echo.
    echo ========================================
    echo Build concluido!
    echo ========================================
    echo.
    echo Para testar:
    echo   cd dist
    echo   main.exe
    echo.
) else (
    echo.
    echo AVISO: Arquivo .env nao encontrado!
    echo Crie o arquivo .env antes de executar o EXE.
    echo.
)

pause
