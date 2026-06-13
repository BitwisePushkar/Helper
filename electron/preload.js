'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getPlatform: () => ipcRenderer.invoke('get-platform'),
  setPosition: (x, y) => ipcRenderer.send('set-position', { x, y }),
  setStealth: (enabled) => ipcRenderer.send('set-stealth', enabled),
  onClearAnswer: (cb) => ipcRenderer.on('clear-answer', cb),
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),
})
