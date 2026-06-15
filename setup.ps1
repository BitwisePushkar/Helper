# ═══════════════════════════════════════════════════════════════════════════════
# Meeting AI — One-shot setup & launcher for Windows
# ═══════════════════════════════════════════════════════════════════════════════

# Set encoding to UTF8 to handle special characters nicely
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ── helper output functions ──────────────────────────────────────────────────
function Write-Info ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Success ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn ($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-ErrorOut ($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; Exit 1 }
function Write-Step ($msg) { Write-Host "`n▶ $msg" -ForegroundColor Blue }

# ── config ────────────────────────────────────────────────────────────────────
$BACKEND_PORT = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { 8000 }
$FRONTEND_PORT = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { 5173 }
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $SCRIPT_DIR) { $SCRIPT_DIR = Get-Location }
$COMPOSE_FILE = Join-Path $SCRIPT_DIR "docker" "docker-compose.yml"
$BACKEND_DIR = Join-Path $SCRIPT_DIR "backend"
$FRONTEND_DIR = Join-Path $SCRIPT_DIR "frontend"
$ELECTRON_DIR = Join-Path $SCRIPT_DIR "electron"

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "1 / 6 — Checking system requirements"
# ─────────────────────────────────────────────────────────────────────────────

# Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-ErrorOut "Docker not found. Install Docker Desktop for Windows from https://docs.docker.com/get-docker/ then re-run."
}
& docker info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorOut "Docker daemon is not running. Start Docker Desktop and re-run."
}
$dockerVer = (docker --version) -replace '.*version\s+([^\s,]+).*','$1'
Write-Success "Docker OK ($dockerVer)"

# Docker Compose v2
& docker compose version >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorOut "Docker Compose v2 not found. Update Docker Desktop or install the plugin."
}
Write-Success "Docker Compose OK"

# Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warn "Node.js not found. Checking if winget is available to install..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing Node.js (LTS) via winget..."
        & winget install OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements
        # Refresh path
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-ErrorOut "Node.js not found. Please install Node.js (LTS) from https://nodejs.org/ and re-run."
    }
}
$nodeVer = & node -v
Write-Success "Node.js OK ($nodeVer)"

# npm
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-ErrorOut "npm not found even though node is installed. Check your PATH."
}
$npmVer = & npm -v
Write-Success "npm OK ($npmVer)"

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "2 / 6 — Setting up environment files"
# ─────────────────────────────────────────────────────────────────────────────

$backendEnv = Join-Path $BACKEND_DIR ".env"
$backendEnvExample = Join-Path $BACKEND_DIR ".env.example"
if (-not (Test-Path $backendEnv)) {
    Copy-Item $backendEnvExample $backendEnv
    Write-Success ".env created from .env.example"
} else {
    Write-Info ".env already exists — skipping"
}

$frontendEnv = Join-Path $FRONTEND_DIR ".env.local"
if (-not (Test-Path $frontendEnv)) {
    $envContent = @"
VITE_API_URL=http://localhost:$BACKEND_PORT
VITE_WS_URL=ws://localhost:$BACKEND_PORT
"@
    Set-Content -Path $frontendEnv -Value $envContent
    Write-Success "frontend .env.local created"
} else {
    Write-Info "frontend .env.local already exists — skipping"
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "3 / 6 — Installing frontend dependencies"
# ─────────────────────────────────────────────────────────────────────────────

Set-Location $FRONTEND_DIR
& npm install --prefer-offline --loglevel warn
Write-Success "Frontend npm packages installed"

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "4 / 6 — Installing Electron dependencies"
# ─────────────────────────────────────────────────────────────────────────────

Set-Location $ELECTRON_DIR
& npm config set ignore-scripts false
& npm install --prefer-offline --loglevel warn --foreground-scripts

$electronPathTxt = Join-Path $ELECTRON_DIR "node_modules" "electron" "path.txt"
$electronDist = Join-Path $ELECTRON_DIR "node_modules" "electron" "dist"

if (-not (Test-Path $electronPathTxt) -or -not (Test-Path $electronDist)) {
    Write-Warn "Electron binary not detected in node_modules. Extracting manually..."
    New-Item -ItemType Directory -Force -Path $electronDist | Out-Null
    
    $cacheDir = Join-Path $env:USERPROFILE ".cache" "electron"
    $cacheZip = $null
    if (Test-Path $cacheDir) {
        $cacheZip = Get-ChildItem -Path $cacheDir -Filter "electron-v*.zip" | Select-Object -First 1
    }
    
    if ($cacheZip -and (Test-Path $cacheZip.FullName)) {
        Write-Info "Found cached Electron zip at $($cacheZip.FullName). Extracting..."
        Expand-Archive -Path $cacheZip.FullName -DestinationPath $electronDist -Force
        Set-Content -Path $electronPathTxt -Value "electron.exe"
        Write-Success "Manual Electron extraction from cache succeeded."
    } else {
        Write-Info "No cached Electron zip found. Downloading and extracting manually..."
        $nodeScript = @"
const { downloadArtifact } = require('@electron/get');
const { version } = require('./node_modules/electron/package.json');
downloadArtifact({ version, artifactName: 'electron' })
  .then(zipPath => {
    console.log('ZIP_PATH:' + zipPath);
    process.exit(0);
  })
  .catch(err => {
    console.error(err);
    process.exit(1);
  });
"@
        $nodeScript | Out-File -FilePath temp_download.js -Encoding utf8
        $zipOutput = & node temp_download.js 2>$null
        Remove-Item -Path temp_download.js -ErrorAction SilentlyContinue
        
        $zipPath = ""
        if ($zipOutput -match "ZIP_PATH:(.*)") {
            $zipPath = $Matches[1].Trim()
        }
        
        if ($zipPath -and (Test-Path $zipPath)) {
            Write-Info "Downloaded Electron zip to $zipPath. Extracting..."
            Expand-Archive -Path $zipPath -DestinationPath $electronDist -Force
            Set-Content -Path $electronPathTxt -Value "electron.exe"
            Write-Success "Manual Electron download and extraction succeeded."
        } else {
            Write-ErrorOut "Could not download and extract Electron automatically."
        }
    }
}
Write-Success "Electron npm packages installed"

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "5 / 6 — Starting Docker services (Redis + Backend)"
# ─────────────────────────────────────────────────────────────────────────────

Set-Location $SCRIPT_DIR

Write-Info "Building backend Docker image (first run may take ~3–5 min)..."
& docker compose -f $COMPOSE_FILE build --quiet backend

Write-Info "Starting Redis..."
& docker compose -f $COMPOSE_FILE up -d redis
Write-Info "Starting backend..."
& docker compose -f $COMPOSE_FILE up -d backend

# Wait for backend health
Write-Info "Waiting for backend API to be ready..."
$elapsed = 0
$healthy = $false
while (-not $healthy -and $elapsed -lt 60) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$BACKEND_PORT/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $healthy = $true
        }
    } catch {
        # Ignore connection failure
    }
    if (-not $healthy) {
        Start-Sleep -Seconds 3
        $elapsed += 3
        Write-Host -NoNewline "."
    }
}
Write-Host ""
if (-not $healthy) {
    Write-ErrorOut "Backend didn't start in time. Check: docker compose -f docker/docker-compose.yml logs backend"
}
Write-Success "Backend API is healthy at http://localhost:$BACKEND_PORT"

# ─────────────────────────────────────────────────────────────────────────────
Write-Step "6 / 6 — Launching the app"
# ─────────────────────────────────────────────────────────────────────────────

Write-Info "Starting Frontend dev server..."
Set-Location $FRONTEND_DIR
$frontendProcess = Start-Process npm -ArgumentList "run dev -- --port $FRONTEND_PORT" -NoNewWindow -PassThru

Start-Sleep -Seconds 2

Write-Info "Starting Electron overlay..."
Set-Location $ELECTRON_DIR
$env:ELECTRON_IS_DEV = "1"
$electronProcess = Start-Process npx -ArgumentList "electron ." -NoNewWindow -PassThru

Write-Success "Meeting AI is running!"
Write-Host ""
Write-Host "Services:" -ForegroundColor Yellow
Write-Host "  Backend API   →  http://localhost:$BACKEND_PORT"
Write-Host "  Backend docs  →  http://localhost:$BACKEND_PORT/docs"
Write-Host "  Redis         →  localhost:6379"
Write-Host ""
Write-Host "Keyboard shortcuts (overlay):" -ForegroundColor Yellow
Write-Host "  Ctrl+Shift+M  →  Toggle overlay visibility"
Write-Host "  Ctrl+Shift+C  →  Clear current answer"
Write-Host ""
Write-Host "To stop everything, press Ctrl+C in this terminal window." -ForegroundColor Yellow
Write-Host ""

try {
    # Keep the script running as long as the Electron process is running
    while (-not $electronProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nShutting down..." -ForegroundColor Cyan
    # Stop frontend process
    if (-not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    # Stop electron process if it's still alive
    if (-not $electronProcess.HasExited) {
        Stop-Process -Id $electronProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
