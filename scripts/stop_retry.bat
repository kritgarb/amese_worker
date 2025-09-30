@echo off
REM Encerra processos Python que estejam rodando retry_failed.py usando PowerShell
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'retry_failed.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

