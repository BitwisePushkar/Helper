#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Meeting AI — One-shot setup & launcher
# Tested on: macOS 13+, Ubuntu 22.04+, Windows (WSL2)
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}▶ $*${NC}"; }

# ── config ────────────────────────────────────────────────────────────────────
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
ELECTRON_DIR="$SCRIPT_DIR/electron"

OS="$(uname -s)"

# ─────────────────────────────────────────────────────────────────────────────
step "1 / 7 — Checking system requirements"
# ─────────────────────────────────────────────────────────────────────────────

# Docker
if ! command -v docker &>/dev/null; then
  error "Docker not found. Install it from https://docs.docker.com/get-docker/ then re-run."
fi
if ! sudo docker info &>/dev/null; then
  error "Docker daemon is not running. Start Docker Desktop (or 'sudo systemctl start docker') and re-run."
fi
success "Docker OK ($(docker --version | awk '{print $3}' | tr -d ','))"

# Docker Compose v2
if ! sudo docker compose version &>/dev/null 2>&1; then
  error "Docker Compose v2 not found. Update Docker Desktop or install the plugin."
fi
success "Docker Compose OK"

# Node.js (for Electron + frontend build)
if ! command -v node &>/dev/null; then
  warn "Node.js not found — installing via nvm..."
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  # shellcheck disable=SC1091
  source "$HOME/.nvm/nvm.sh"
  nvm install --lts
fi
NODE_VER=$(node -v)
success "Node.js OK ($NODE_VER)"

# npm
if ! command -v npm &>/dev/null; then
  error "npm not found even though node is installed. Check your PATH."
fi
success "npm OK ($(npm -v))"

# ─────────────────────────────────────────────────────────────────────────────
step "2 / 7 — Setting up environment files"
# ─────────────────────────────────────────────────────────────────────────────

if [ ! -f "$BACKEND_DIR/.env" ]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  success ".env created from .env.example"
else
  info ".env already exists — skipping"
fi

# Frontend env
FRONTEND_ENV="$FRONTEND_DIR/.env.local"
if [ ! -f "$FRONTEND_ENV" ]; then
  cat > "$FRONTEND_ENV" <<EOF
VITE_API_URL=http://localhost:$BACKEND_PORT
VITE_WS_URL=ws://localhost:$BACKEND_PORT
EOF
  success "frontend .env.local created"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "3 / 7 — Installing frontend dependencies"
# ─────────────────────────────────────────────────────────────────────────────

cd "$FRONTEND_DIR"
npm install --prefer-offline --loglevel warn
success "Frontend npm packages installed"
# ─────────────────────────────────────────────────────────────────────────────
step "4 / 7 — Installing Electron dependencies"
# ─────────────────────────────────────────────────────────────────────────────

cd "$ELECTRON_DIR"
npm config set ignore-scripts false
npm install --prefer-offline --loglevel warn --foreground-scripts || true

# Verify and fix Electron installation if needed
if [ ! -f "$ELECTRON_DIR/node_modules/electron/path.txt" ] || [ ! -d "$ELECTRON_DIR/node_modules/electron/dist" ]; then
  warn "Electron binary not detected in node_modules. Extracting manually..."
  mkdir -p "$ELECTRON_DIR/node_modules/electron/dist"
  
  # Try to find a cached Electron zip
  CACHE_ZIP=$(find ~/.cache/electron/ -name "electron-v*.zip" 2>/dev/null | head -n 1 || true)
  
  if [ -n "$CACHE_ZIP" ] && [ -f "$CACHE_ZIP" ]; then
    info "Found cached Electron zip at $CACHE_ZIP. Extracting..."
    unzip -q -o "$CACHE_ZIP" -d "$ELECTRON_DIR/node_modules/electron/dist"
    node -e "
      const fs = require('fs');
      const os = require('os');
      const platform = os.platform();
      const platformPath = platform === 'darwin' ? 'Electron.app/Contents/MacOS/Electron' : (platform === 'win32' ? 'electron.exe' : 'electron');
      fs.writeFileSync('node_modules/electron/path.txt', platformPath);
    "
    success "Manual Electron extraction from cache succeeded."
  else
    info "No cached Electron zip found. Downloading and extracting manually..."
    # Download the artifact using the node API (does not trigger extract-zip)
    node -e "
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
    " > temp_zip_path.txt || true
    
    ZIP_PATH=$(grep "ZIP_PATH:" temp_zip_path.txt | cut -d':' -f2- || true)
    rm -f temp_zip_path.txt
    
    if [ -n "$ZIP_PATH" ] && [ -f "$ZIP_PATH" ]; then
      info "Downloaded Electron zip to $ZIP_PATH. Extracting..."
      unzip -q -o "$ZIP_PATH" -d "$ELECTRON_DIR/node_modules/electron/dist"
      node -e "
        const fs = require('fs');
        const os = require('os');
        const platform = os.platform();
        const platformPath = platform === 'darwin' ? 'Electron.app/Contents/MacOS/Electron' : (platform === 'win32' ? 'electron.exe' : 'electron');
        fs.writeFileSync('node_modules/electron/path.txt', platformPath);
      "
      success "Manual Electron download and extraction succeeded."
    else
      error "Could not download and extract Electron automatically."
    fi
  fi
fi

success "Electron npm packages installed"

# ─────────────────────────────────────────────────────────────────────────────
step "5 / 6 — Starting Docker services (Redis + Backend)"
# ─────────────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

info "Stopping any existing containers..."
sudo docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true

info "Freeing ports if occupied..."
# Stop system Redis if running (systemd will keep respawning it otherwise)
if sudo systemctl is-active redis-server &>/dev/null; then
  warn "System Redis service is running — stopping it..."
  sudo systemctl stop redis-server
  sudo systemctl disable redis-server 2>/dev/null || true
fi
if sudo systemctl is-active redis &>/dev/null; then
  sudo systemctl stop redis
  sudo systemctl disable redis 2>/dev/null || true
fi

for PORT in 6379 $BACKEND_PORT; do
  PID=$(sudo lsof -ti :"$PORT" 2>/dev/null || true)
  if [ -n "$PID" ]; then
    warn "Port $PORT in use (PID $PID) — killing..."
    sudo kill -9 $PID 2>/dev/null || true
  fi
done
sleep 2

info "Building backend Docker image (first run may take ~3–5 min)..."
sudo docker compose -f "$COMPOSE_FILE" build --quiet backend

info "Starting all services..."
sudo docker compose -f "$COMPOSE_FILE" up -d

# Wait for backend health
info "Waiting for backend API to be ready..."
ELAPSED=0
until curl -sf "http://localhost:$BACKEND_PORT/health" &>/dev/null; do
  if [ $ELAPSED -ge 60 ]; then
    error "Backend didn't start in time. Check: docker compose -f docker/docker-compose.yml logs backend"
  fi
  sleep 3
  ELAPSED=$((ELAPSED + 3))
  printf '.'
done
echo ""
success "Backend API is healthy at http://localhost:$BACKEND_PORT"

# ─────────────────────────────────────────────────────────────────────────────
step "6 / 6 — Launching the app"
# ─────────────────────────────────────────────────────────────────────────────

# macOS: set up virtual audio device if BlackHole not present
if [ "$OS" = "Darwin" ]; then
  if ! system_profiler SPAudioDataType 2>/dev/null | grep -qi "BlackHole"; then
    warn "BlackHole virtual audio driver not found."
    warn "Install it to capture meeting audio from Zoom/Teams/Meet:"
    warn "  brew install blackhole-2ch"
    warn "Continuing with mic-only capture for now."
  else
    success "BlackHole virtual audio device found"
  fi
fi

# Windows WSL2 notice
if grep -qi microsoft /proc/version 2>/dev/null; then
  warn "Running in WSL2 — Electron must be launched from the Windows side."
  warn "Run: cd electron && npx electron . in a Windows terminal."
fi

info "Starting Frontend dev server..."
cd "$FRONTEND_DIR"
npm run dev -- --port $FRONTEND_PORT &
FRONTEND_PID=$!

# Wait briefly for frontend to start
sleep 2

# Fix Electron sandbox permissions on Linux
if [ "$OS" = "Linux" ]; then
  CHROME_SANDBOX="$ELECTRON_DIR/node_modules/electron/dist/chrome-sandbox"
  if [ -f "$CHROME_SANDBOX" ]; then
    sudo chown root:root "$CHROME_SANDBOX"
    sudo chmod 4755 "$CHROME_SANDBOX"
  fi
fi

info "Starting Electron overlay..."
cd "$ELECTRON_DIR"
ELECTRON_IS_DEV=1 npx electron . &
ELECTRON_PID=$!

success "Meeting AI is running!"
echo ""
echo -e "${BOLD}Services:${NC}"
echo -e "  Backend API   →  http://localhost:$BACKEND_PORT"
echo -e "  Backend docs  →  http://localhost:$BACKEND_PORT/docs"
echo -e "  Redis         →  localhost:6379"
echo ""
echo -e "${BOLD}Keyboard shortcuts (overlay):${NC}"
echo -e "  Ctrl+Shift+M  →  Toggle overlay visibility"
echo -e "  Ctrl+Shift+C  →  Clear current answer"
echo ""
echo -e "${YELLOW}To stop everything:${NC}"
echo -e "  ./teardown.sh"
echo ""

# Keep script alive; Ctrl-C shuts Electron and Frontend
trap 'echo ""; info "Shutting down..."; kill $ELECTRON_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait $ELECTRON_PID
