import {app,BrowserWindow,shell} from 'electron';
import path from 'node:path';

const createWindow=()=>{
  const win=new BrowserWindow({
    width:1440,height:900,minWidth:1024,minHeight:680,
    backgroundColor:'#070709',titleBarStyle:'hiddenInset',
    webPreferences:{contextIsolation:true,nodeIntegration:false}
  });
  if(!app.isPackaged){
    win.loadURL('http://localhost:5173');
  }else{
    win.loadFile(path.join(process.resourcesPath,'web','index.html'));
  }
  win.webContents.setWindowOpenHandler(({url})=>{shell.openExternal(url);return{action:'deny'}});
};
app.whenReady().then(()=>{createWindow();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow()})});
app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
