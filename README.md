# Meeting AI

An invisible AI overlay that listens to your meetings, detects questions directed at you, and streams answers in real time — invisible to screen share. Also includes a manual query bar to type questions directly and get instant AI-generated answers.

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

## Features

- Real-time audio transcription via local Whisper model (no data leaves your machine)
- Automatic question detection (heuristic + LLM-based)
- Streaming AI answers displayed in an overlay
- Manual query bar — type any question and get an instant answer (bypasses detection logic)
- Screen share stealth on Windows and macOS
- Keyboard shortcuts to toggle visibility and clear answers
- Auto port-conflict resolution on startup
- Works with Zoom, Google Meet, Teams, Webex, HackerRank, LeetCode

---

## Quick start (one command)

1. Set your Gemini API key in `backend/.env` (or copy `backend/.env.example` to `backend/.env` and fill it in):
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

2. Run the setup script:

   **On macOS / Linux:**
   ```bash
   git clone https://github.com/BitwisePushkar/Helper.git
   cd Helper
   chmod +x setup.sh teardown.sh
   ./setup.sh
   ```

   **On Windows (PowerShell):**
   ```powershell
   git clone https://github.com/BitwisePushkar/Helper.git
   cd Helper
   Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
   .\setup.ps1
   ```

That's it. The script handles everything in order:
1. Checks Docker, Node.js
2. Creates `.env` files (if not present)
3. Installs npm packages
4. Stops conflicting services and frees occupied ports
5. Builds and starts Docker services (Redis, Backend)
6. Fixes Electron sandbox permissions (Linux)
7. Launches the Electron overlay

---

## Prerequisites — install these before running setup

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
# 1. Docker Desktop for Windows
# Download from https://www.docker.com/products/docker-desktop/

# 2. Node.js LTS
# Download from https://nodejs.org/ (or will auto-install via winget if setup.ps1 runs)

# 3. VB-Cable (virtual audio, free)
# Download from https://vb-audio.com/Cable/
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

**On macOS / Linux:**
```bash
GEMINI_MODEL=gemini-3.1-flash-lite ./setup.sh # Default — fast and efficient
GEMINI_MODEL=gemini-2.5-flash ./setup.sh      # Better code generation
GEMINI_MODEL=gemini-3.1-flash ./setup.sh      # Higher quality answers
```

**On Windows (PowerShell):**
```powershell
$env:GEMINI_MODEL="gemini-3.1-flash-lite"; .\setup.ps1
$env:GEMINI_MODEL="gemini-2.5-flash"; .\setup.ps1
$env:GEMINI_MODEL="gemini-3.1-flash"; .\setup.ps1
```

---

## Project structure

```
Helper/
├── setup.sh                    ← Run this on macOS / Linux
├── setup.ps1                   ← Run this on Windows
├── teardown.sh                 ← Tear down on macOS / Linux
├── teardown.ps1                ← Tear down on Windows
├── docker/
│   └── docker-compose.yml      ← Redis + Backend
├── backend/
│   ├── main.py                 ← FastAPI app + WebSocket
│   ├── ai/llm.py               ← LangChain + Gemini question detection + streaming
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
│       └── components/
│           ├── AnswerPanel.jsx ← Streaming answer display
│           ├── TranscriptFeed.jsx ← Live transcript
│           ├── Controls.jsx    ← Start/stop buttons
│           ├── QueryBar.jsx    ← Manual question input
│           └── StatusBadge.jsx ← Connection status
└── electron/
    ├── main.js                 ← Window creation + stealth + IPC
    └── preload.js              ← Secure context bridge
```

---

## How it works

1. **Audio capture** — Browser mic or system audio (via loopback device) is captured and sent to the backend
2. **Transcription** — faster-whisper converts audio to text locally (no cloud dependency)
3. **Question detection** — Two-stage system:
   - Heuristic regex checks for question words and CS terms (fast, no API call)
   - Falls back to Gemini LLM for ambiguous lines
4. **Answer streaming** — Gemini generates a concise answer, streamed token-by-token to the overlay
5. **Manual query** — Type directly in the query bar to bypass detection and get instant answers

---

## WebSocket protocol

The backend exposes `ws://localhost:8000/ws/{session_id}`.

**Client → Server:**
```json
{ "type": "transcript", "text": "Can you walk us through your approach?", "speaker": "interviewer" }
{ "type": "question", "text": "explain binary search" }
{ "type": "audio_chunk", "data": "<base64 encoded audio>" }
{ "type": "ping" }
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

| Frame type | Behavior |
|---|---|
| `transcript` | Appends to context, runs question detection (3+ words required) |
| `question` | Skips all detection, goes straight to answer generation |
| `audio_chunk` | Decoded via FFmpeg, transcribed via Whisper, then treated as transcript |

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health (Redis + Gemini status) |
| GET | `/new-session` | Generate a new session UUID |
| GET | `/session/{id}/context` | Get rolling transcript context |
| DELETE | `/session/{id}` | Clear session from Redis |
| POST | `/capture/start` | Start system audio capture |
| POST | `/capture/stop` | Stop system audio capture |
| WS | `/ws/{id}` | Main real-time connection |

---

## Screen share stealth

The overlay is excluded from screen capture using OS-native APIs called via Electron:

- **Windows** — `setContentProtection(true)` → `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`
- **macOS** — `setContentProtection(true)` → `CGSSetWindowSharingState(kCGSDoNotShare)`
- **Linux** — Not supported at OS level. Share a specific window (not full screen) in your meeting app to keep the overlay hidden.

Tested on Zoom, Google Meet, Microsoft Teams, and Webex.

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+M` (or `Cmd+Shift+M`) | Toggle overlay visibility |
| `Ctrl+Shift+C` | Clear current answer |

---

## Question detection triggers

The heuristic detects these patterns without calling the LLM:

- Any line ending with `?`
- Question words: `who`, `what`, `where`, `when`, `why`, `how`, `can`, `could`, `would`, `should`, `do`, `does`, `did`, `is`, `are`, `was`, `were`, `have`, `has`, `had`, `will`, `shall`
- Action words: `explain`, `define`, `describe`, `tell me`
- CS/Technical terms: `binary`, `search`, `algorithm`, `sort`, `tree`, `graph`, `hash`, `cache`, `database`, `sql`, `index`, `array`, `list`, `stack`, `queue`, `complexity`, `big o`, `dp`, `recursion`, `heap`

Lines with fewer than 3 words are ignored (filters out filler like "ok", "yeah", "um").

---

## Troubleshooting

**Gemini API key issues / LLM not responding**
- Ensure `GEMINI_API_KEY` is correctly set in `backend/.env`.
- Check backend logs:
  ```bash
  sudo docker compose -f docker/docker-compose.yml logs backend
  ```
- Query the `/health` endpoint to inspect connection status:
  ```bash
  curl http://localhost:8000/health
  ```

**Backend unhealthy**
```bash
sudo docker compose -f docker/docker-compose.yml logs backend
```

**Port 6379 already in use (Redis conflict)**
- The setup script handles this automatically now. If it still fails:
  ```bash
  sudo systemctl stop redis-server
  sudo systemctl disable redis-server
  ```

**No audio captured**
- macOS: Ensure BlackHole is installed and Multi-Output Device is configured
- Windows: VB-Cable must be selected as the playback device in meeting app settings
- Linux: Use `pavucontrol` to route meeting app audio to the monitor source

**Electron window not appearing**
- Press `Ctrl+Shift+M` — the window may be hidden
- Check the tray icon (system tray / menu bar)

**Electron SUID sandbox error (Linux)**
- The setup script fixes this automatically. If running manually:
  ```bash
  sudo chown root:root electron/node_modules/electron/dist/chrome-sandbox
  sudo chmod 4755 electron/node_modules/electron/dist/chrome-sandbox
  ```

**Port conflicts (custom ports)**
```bash
# Backend port
BACKEND_PORT=8080 ./setup.sh
# Frontend dev server
FRONTEND_PORT=3000 ./setup.sh
```

---

## Stopping everything

**On macOS / Linux:**
```bash
./teardown.sh
```

**On Windows (PowerShell):**
```powershell
.\teardown.ps1
```

To also wipe downloaded models and caches:
```bash
sudo docker compose -f docker/docker-compose.yml down -v
```
