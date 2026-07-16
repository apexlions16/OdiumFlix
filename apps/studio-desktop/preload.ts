import {contextBridge,ipcRenderer} from 'electron';
contextBridge.exposeInMainWorld('odiumStudio',{
  selectMedia:()=>ipcRenderer.invoke('studio:select-media'),
  startBatch:(payload:unknown)=>ipcRenderer.invoke('studio:start-batch',payload)
});
