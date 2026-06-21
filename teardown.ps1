# Set encoding to UTF8 to handle special characters nicely
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Info ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Success ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $SCRIPT_DIR) { $SCRIPT_DIR = Get-Location }
$COMPOSE_FILE = Join-Path $SCRIPT_DIR "docker" "docker-compose.yml"

Write-Info "Stopping Docker services..."
& docker compose -f $COMPOSE_FILE down --remove-orphans

Write-Info "Stopping any lingering Electron/Node/Vite processes..."
# Stop electron processes
Get-Process -Name "electron" -ErrorAction SilentlyContinue | Stop-Process -Force

# Find node processes starting frontend/Vite or Electron packages and stop them
if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -like "*vite*" -or $_.CommandLine -like "*electron*") {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Get-WmiObject Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -like "*vite*" -or $_.CommandLine -like "*electron*") {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

# Free ports if still occupied
Write-Info "Freeing ports if still occupied..."
foreach ($port in @(6379, 8000)) {
    $proc = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Write-Success "All services stopped. Data in Docker volumes is preserved."
Write-Host "To also delete Gemini model cache and Whisper cache:" -ForegroundColor Yellow
Write-Host "  docker compose -f docker/docker-compose.yml down -v"
