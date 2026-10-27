# Daily NBA data sync for Windows. Register it once (runs every day at 06:00):
#   schtasks /Create /SC DAILY /ST 06:00 /TN "FantaBall daily sync" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"%CD%\scripts\daily-sync.ps1\""
# Safe to run twice: a database lock allows only one sync at a time.
Set-Location (Join-Path $PSScriptRoot "..")
$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $python -m flask --app app nba daily
exit $LASTEXITCODE
