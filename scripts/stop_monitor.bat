@echo off
REM Encerra processos Python que estejam rodando monitor_bemsoft.py usando PowerShell
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'monitor_bemsoft.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

