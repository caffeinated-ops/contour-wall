const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('launcher', {
  launchGame: (key, playerName) => ipcRenderer.invoke('launch-game', { key, playerName }),
});
