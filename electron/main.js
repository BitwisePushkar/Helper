'use strict'

const {
  app,
  BrowserWindow,
  ipcMain,
  screen,
  globalShortcut,
  Tray,
  Menu,
  nativeImage,
} = require('electron')
const path = require('path')
const { spawn } = require('child_process')

const fs = require('fs')

const IS_DEV = process.env.ELECTRON_IS_DEV === '1'
const IS_MAC = process.platform === 'darwin'
const IS_WIN = process.platform === 'win32'

// ── backend sidecar ─────────────────────────────────────────────────────────
let backendProc = null

function startBackend() {
  if (IS_DEV) return // assume docker-compose is running in dev

  const backendPath = path.join(__dirname, '..', 'backend')
  
  let uvicornExec = 'uvicorn'
  const venvPath1 = path.join(backendPath, '.venv')
  const venvPath2 = path.join(backendPath, 'venv')

  if (fs.existsSync(venvPath1)) {
    uvicornExec = path.join(venvPath1, IS_WIN ? 'Scripts' : 'bin', 'uvicorn')
  } else if (fs.existsSync(venvPath2)) {
    uvicornExec = path.join(venvPath2, IS_WIN ? 'Scripts' : 'bin', 'uvicorn')
  }

  backendProc = spawn(uvicornExec, ['main:app', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: backendPath,
    stdio: 'inherit',
    env: { ...process.env },
  })

  backendProc.on('error', (err) => {
    console.error('[Backend] Failed to start:', err.message)
  })

  backendProc.on('exit', (code) => {
    if (code !== 0) console.error(`[Backend] Exited with code ${code}`)
  })
}

function stopBackend() {
  if (backendProc) {
    backendProc.kill('SIGTERM')
    backendProc = null
  }
}

// ── overlay window ──────────────────────────────────────────────────────────
let overlayWin = null
let tray = null

function createOverlayWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize

  overlayWin = new BrowserWindow({
    width: 440,
    height: 600,

    // Position: top-right corner
    x: width - 460,
    y: 20,

    // Overlay properties
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    movable: true,

    // *** STEALTH: exclude from screen capture ***
    // On Windows this calls SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
    // On macOS this calls CGSSetWindowSharingState(kCGSDoNotShare)
    contentProtection: true,

    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // Allow media access in renderer for mic fallback
      nodeIntegrationInWorker: false,
    },
  })

  // Load the React app
  if (IS_DEV) {
    overlayWin.loadURL('http://localhost:5173')
  } else {
    overlayWin.loadFile(
      path.join(__dirname, '..', 'resources', 'frontend', 'index.html')
    )
  }

  // Keep always-on-top across all workspaces (macOS)
  if (IS_MAC) {
    overlayWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  }

  overlayWin.on('closed', () => {
    overlayWin = null
  })
}

// ── tray icon ───────────────────────────────────────────────────────────────
function createTray() {
  // Minimal 16x16 transparent icon (replace with real icon in assets/)
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('Meeting AI')

  const menu = Menu.buildFromTemplate([
    {
      label: 'Show / Hide',
      click: () => {
        if (!overlayWin) return
        overlayWin.isVisible() ? overlayWin.hide() : overlayWin.show()
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        app.quit()
      },
    },
  ])
  tray.setContextMenu(menu)
}

// ── global shortcuts ─────────────────────────────────────────────────────────
function registerShortcuts() {
  // Cmd/Ctrl+Shift+M — toggle overlay visibility
  globalShortcut.register('CommandOrControl+Shift+M', () => {
    if (!overlayWin) return
    overlayWin.isVisible() ? overlayWin.hide() : overlayWin.show()
  })

  // Cmd/Ctrl+Shift+C — clear current answer
  globalShortcut.register('CommandOrControl+Shift+C', () => {
    overlayWin?.webContents.send('clear-answer')
  })
}

// ── IPC handlers ─────────────────────────────────────────────────────────────
function registerIPC() {
  // Renderer can ask for platform info
  ipcMain.handle('get-platform', () => process.platform)

  // Renderer can request overlay to move
  ipcMain.on('set-position', (_event, { x, y }) => {
    overlayWin?.setPosition(x, y)
  })

  // Renderer can toggle content protection at runtime
  ipcMain.on('set-stealth', (_event, enabled) => {
    overlayWin?.setContentProtection(enabled)
  })
}

// ── app lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  startBackend()
  createOverlayWindow()
  createTray()
  registerShortcuts()
  registerIPC()
})

app.on('window-all-closed', () => {
  // Keep running in tray on macOS
  if (!IS_MAC) app.quit()
})

app.on('activate', () => {
  if (!overlayWin) createOverlayWindow()
})

app.on('before-quit', () => {
  globalShortcut.unregisterAll()
  stopBackend()
})

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    overlayWin?.show()
    overlayWin?.focus()
  })
}
