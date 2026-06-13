#!/usr/bin/env bash
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

COMPOSE_FILE="$(dirname "$0")/docker/docker-compose.yml"

info "Stopping Docker services..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans

info "Killing any lingering Electron processes..."
pkill -f "electron ." 2>/dev/null || true

info "Killing any lingering Vite/Frontend processes..."
pkill -f "vite" 2>/dev/null || true

success "All services stopped. Data in Docker volumes is preserved."
echo "To also delete Ollama model cache and Whisper cache:"
echo "  docker compose -f docker/docker-compose.yml down -v"
