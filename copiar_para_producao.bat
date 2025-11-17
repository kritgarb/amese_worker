@echo off
chcp 65001 >nul
cls
echo.
echo ================================================
echo   Copiar Projeto para Produção
echo ================================================
echo.

set "ORIGEM=%~dp0"
set "DESTINO=C:\Users\Administrator\Desktop\amese_worker\"

echo Origem:  %ORIGEM%
echo Destino: %DESTINO%
echo.

REM Cria diretório de destino se não existir
if not exist "%DESTINO%" (
    echo [INFO] Criando diretório de destino...
    mkdir "%DESTINO%"
)

echo [INFO] Copiando arquivos...

REM Copia arquivos essenciais
copy "%ORIGEM%.env" "%DESTINO%.env" >nul
copy "%ORIGEM%main.py" "%DESTINO%main.py" >nul
copy "%ORIGEM%requirements.txt" "%DESTINO%requirements.txt" >nul
copy "%ORIGEM%install_service.bat" "%DESTINO%install_service.bat" >nul
copy "%ORIGEM%uninstall_service.bat" "%DESTINO%uninstall_service.bat" >nul
copy "%ORIGEM%tests_map.json" "%DESTINO%tests_map.json" >nul
copy "%ORIGEM%README_SERVICO.md" "%DESTINO%README_SERVICO.md" >nul

echo [OK] Arquivos principais copiados

REM Copia pasta src
echo [INFO] Copiando pasta src...
if not exist "%DESTINO%src" mkdir "%DESTINO%src"
xcopy "%ORIGEM%src\*.*" "%DESTINO%src\" /Y /Q >nul
echo [OK] Pasta src copiada

REM Copia pasta completo
echo [INFO] Copiando pasta completo...
if not exist "%DESTINO%completo" mkdir "%DESTINO%completo"
if not exist "%DESTINO%completo\failed_events" mkdir "%DESTINO%completo\failed_events"
echo [OK] Pasta completo criada

echo.
echo ================================================
echo   PRÓXIMOS PASSOS:
echo ================================================
echo.
echo 1. Vá para: %DESTINO%
echo.
echo 2. Crie o ambiente virtual:
echo    python -m venv .venv
echo.
echo 3. Ative o ambiente virtual:
echo    .venv\Scripts\activate
echo.
echo 4. Instale as dependências:
echo    pip install -r requirements.txt
echo.
echo 5. Instale o serviço:
echo    Clique com botão direito em install_service.bat
echo    Selecione "Executar como administrador"
echo.
echo ================================================
echo.
pause
