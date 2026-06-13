# Meeting AI

An invisible AI overlay that listens to your meetings, detects questions directed at you, and streams answers in real time — invisible to screen share.

---

## What's inside

| Layer | Tech |
|---|---|
| Desktop app | Electron (stealth overlay) |
| UI | React 18 + Vite + Tailwind |
| Backend API | FastAPI + Python 3.11 |
| Transcription | faster-whisper (local, runs in Docker) |
| LLM | Gemini API + LangChain Google GenAI |
| Session memory | Redis (in-memory only, no disk) |
| Orchestration | Docker Compose |

---

## Quick start (one command)

1. Set your Gemini API key in `backend/.env` (or copy `backend/.env.example` to `backend/.env` and fill it in):
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

2. Run the setup script:
   ```bash
   git clone <repo>
   cd meeting-ai
   chmod +x setup.sh teardown.sh
   ./setup.sh
   ```

That's it. The script handles everything in order:
1. Checks Docker, Node.js
2. Creates `.env` files (if not present)
3. Installs npm packages
4. Builds and starts Docker services (Redis, Backend)
5. Launches the Electron overlay

---

## Prerequisites — install these before running setup.sh

### macOS

```bash
# 1. Docker Desktop
# Download from https://www.docker.com/products/docker-desktop/

# 2. Node.js (LTS)
brew install node

# 3. Virtual audio driver (to capture meeting app audio, not just mic)
brew install blackhole-2ch
# After install, go to: Audio MIDI Setup → Create Multi-Output Device
# Combine your speakers + BlackHole 2ch
# Set that as your system output in System Settings → Sound

# 4. Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Windows

```powershell
# 1. Docker Desktop with WSL2 backend
# Download from https://www.docker.com/products/docker-desktop/

# 2. Node.js LTS
# Download from https://nodejs.org/

# 3. VB-Cable (virtual audio, free)
# Download from https://vb-audio.com/Cable/

# ⚠ Electron must run from Windows (not inside WSL2)
# Run setup.sh from Git Bash or WSL2, but launch Electron from Windows terminal:
#   cd electron && npx electron .
```

### Linux (Ubuntu 22.04+)

```bash
# 1. Docker
sudo apt-get install docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# Log out and back in

# 2. Node.js
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3. Audio
sudo apt-get install -y pulseaudio pavucontrol
# Use pavucontrol to route meeting app audio to the monitor source
```

---

## Changing the AI model

Edit `backend/.env` or pass as env variable:

```bash
GEMINI_MODEL=gemini-3.1-flash-lite ./setup.sh # Default — fast and efficient
GEMINI_MODEL=gemini-3.1-flash ./setup.sh      # Higher quality answers
```

---

## Project structure

```
meeting-ai/
├── setup.sh                    ← Run this
├── teardown.sh
├── docker/
│   └── docker-compose.yml      ← Redis + Backend
├── backend/
│   ├── main.py                 ← FastAPI app + WebSocket
│   ├── ai/llm.py               ← LangChain + Ollama question detection + streaming
│   ├── audio/capture.py        ← sounddevice mic + loopback capture
│   ├── audio/transcriber.py    ← faster-whisper STT
│   ├── session/redis_store.py  ← rolling transcript buffer
│   ├── config.py               ← pydantic-settings
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx             ← Main overlay UI
│       ├── hooks/useWebSocket.js
│       ├── hooks/useAudioCapture.js
│       └── components/         ← AnswerPanel, TranscriptFeed, Controls
└── electron/
    ├── main.js                 ← Window creation + stealth + IPC
    └── preload.js              ← Secure context bridge
```

---

## WebSocket protocol

The backend exposes `ws://localhost:8000/ws/{session_id}`.

**Client → Server:**
```json
{ "type": "transcript", "text": "Can you walk us through your approach?", "speaker": "interviewer" }
{ "type": "ping" }
{ "type": "stop" }
```

**Server → Client:**
```json
{ "type": "transcript_ack", "text": "..." }
{ "type": "question_detected", "text": "..." }
{ "type": "answer_token", "token": "The approach I took..." }
{ "type": "answer_done" }
{ "type": "pong" }
{ "type": "error", "message": "..." }
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health (Redis + Ollama status) |
| GET | `/new-session` | Generate a new session UUID |
| GET | `/session/{id}/context` | Get rolling transcript context |
| DELETE | `/session/{id}` | Clear session from Redis |
| WS | `/ws/{id}` | Main real-time connection |

---

## Screen share stealth

The overlay is excluded from screen capture using OS-native APIs called via Electron:

- **Windows** — `setContentProtection(true)` → `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`
- **macOS** — `setContentProtection(true)` → `CGSSetWindowSharingState(kCGSDoNotShare)`

Tested on Zoom, Google Meet, Microsoft Teams, and Webex.

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+M` (or `Cmd+Shift+M`) | Toggle overlay visibility |
| `Ctrl+Shift+C` | Clear current answer |

---

## Troubleshooting

**Gemini API key issues / LLM not responding**
- Ensure `GEMINI_API_KEY` is correctly set in `backend/.env`.
- Check backend logs:
  ```bash
  docker compose -f docker/docker-compose.yml logs backend
  ```
- Query the `/health` endpoint to inspect connection status:
  ```bash
  curl http://localhost:8000/health
  ```

**Backend unhealthy**
```bash
docker compose -f docker/docker-compose.yml logs backend
```

**No audio captured**
- macOS: Ensure BlackHole is installed and Multi-Output Device is configured
- Windows: VB-Cable must be selected as the playback device in meeting app settings
- Linux: Use `pavucontrol` to route audio to the monitor source

**Electron window not appearing**
- Press `Ctrl+Shift+M` — the window may be hidden
- Check the tray icon (system tray / menu bar)

**Port conflicts**
```bash
# Backend port
BACKEND_PORT=8080 ./setup.sh
# Frontend dev server
FRONTEND_PORT=3000 ./setup.sh
```

---

## Stopping everything

```bash
./teardown.sh
```

To also wipe downloaded models and caches:
```bash
docker compose -f docker/docker-compose.yml down -v
```
