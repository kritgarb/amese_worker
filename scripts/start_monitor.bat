@echo off
setlocal

REM Ativa venv se existir
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
)

python monitor_bemsoft.py

endlocal

