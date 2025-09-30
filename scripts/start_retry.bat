@echo off
setlocal

set DIR=%1
if "%DIR%"=="" set DIR=completo/failed_events

if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
)

python retry_failed.py --dir "%DIR%"

endlocal

