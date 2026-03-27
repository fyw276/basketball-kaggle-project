# Activate virtual environment
$venvPath = "$env:USERPROFILE\.virtualenvs\clothing-assistant\Scripts\Activate.ps1"
& $venvPath
Write-Host "Virtual environment activated: $env:USERPROFILE\.virtualenvs\clothing-assistant" -ForegroundColor Green
