import {contextBridge, ipcRenderer} from 'electron';

contextBridge.exposeInMainWorld('odiumStudio', {
  selectMedia: () => ipcRenderer.invoke('studio:select-media'),
  selectAudio: () => ipcRenderer.invoke('studio:select-audio'),
  selectSubtitles: () => ipcRenderer.invoke('studio:select-subtitles'),
  startBatch: (payload:unknown) => ipcRenderer.invoke('studio:start-batch', payload),
  fetchMetadata: (payload:unknown) => ipcRenderer.invoke('studio:fetch-metadata', payload),
});
