@echo off
REM Encerra processos Python que estejam rodando main.py usando PowerShell
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'main.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
