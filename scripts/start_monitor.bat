@echo off
setlocal

REM Ativa venv se existir
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
)

set PYTHONPATH=%~dp0\..\src
python %~dp0\..\main.py

endlocal
