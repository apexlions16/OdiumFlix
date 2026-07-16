import {app,BrowserWindow,dialog,ipcMain,shell} from 'electron';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';
import ffprobeStatic from 'ffprobe-static';

type Row={localPath?:string;fileName:string;title:string;type:string;sourceQuality:string;targets:string[];imdbId?:string;season?:number;episode?:number};
type Settings={hfRepo:string;githubRepo:string;hfToken:string;githubToken:string;outputDir?:string};
type Payload={rows:Row[];settings:Settings};

const createWindow=()=>{const win=new BrowserWindow({width:1500,height:940,minWidth:1050,minHeight:700,backgroundColor:'#08080c',title:'OdiumFlix Studio',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});if(!app.isPackaged)win.loadURL('http://localhost:5174');else win.loadFile(path.join(process.resourcesPath,'studio','index.html'));win.webContents.setWindowOpenHandler(({url})=>{shell.openExternal(url);return{action:'deny'}})};

ipcMain.handle('studio:select-media',async()=>{const result=await dialog.showOpenDialog({properties:['openFile','multiSelections'],filters:[{name:'Media',extensions:['mkv','mp4','mov','m4v','webm']}]});if(result.canceled)return[];return result.filePaths.map(file=>({name:path.basename(file),path:file,size:fs.statSync(file).size}))});

const workerCommand=()=>{if(app.isPackaged){const exe=path.join(process.resourcesPath,'worker',process.platform==='win32'?'odium-media.exe':'odium-media');if(fs.existsSync(exe))return{cmd:exe,args:[]}}const script=path.resolve(__dirname,'../../../tools/media_pipeline/odium_media.py');return{cmd:process.platform==='win32'?'py':'python3',args:process.platform==='win32'?['-3',script]:[script]}};

ipcMain.handle('studio:start-batch',async(_event,payload:Payload)=>{if(!payload.rows.length)return{ok:false,message:'Batch boş.'};const invalid=payload.rows.find(row=>!row.localPath);if(invalid)return{ok:false,message:`${invalid.fileName} için yerel dosya yolu alınamadı. Windows Studio içinden tekrar seç.`};const root=payload.settings.outputDir||path.join(app.getPath('videos'),'OdiumFlix','processed');fs.mkdirSync(root,{recursive:true});const configPath=path.join(app.getPath('temp'),`odiumflix-batch-${Date.now()}.json`);const logPath=path.join(app.getPath('logs'),`media-${Date.now()}.log`);const config={items:payload.rows.map(row=>({source:row.localPath,title:row.title,content_type:row.type,source_quality:row.sourceQuality,target_qualities:row.targets,imdb_id:row.imdbId||undefined,season:row.season,episode:row.episode}))};fs.writeFileSync(configPath,JSON.stringify(config,null,2));const worker=workerCommand();const args=[...worker.args,'batch',configPath,'--output',root,'--message',`OdiumFlix Studio batch ${new Date().toISOString()}`];if(payload.settings.hfRepo)args.push('--hf-repo',payload.settings.hfRepo);if(payload.settings.githubRepo)args.push('--github-repo',payload.settings.githubRepo);const env={...process.env,HF_TOKEN:payload.settings.hfToken||process.env.HF_TOKEN,GITHUB_TOKEN:payload.settings.githubToken||process.env.GITHUB_TOKEN,HF_XET_HIGH_PERFORMANCE:'1',ODIUM_FFMPEG:ffmpegPath||'ffmpeg',ODIUM_FFPROBE:ffprobeStatic.path||'ffprobe'};return await new Promise(resolve=>{const log=fs.createWriteStream(logPath,{flags:'a'});const child=spawn(worker.cmd,args,{env,windowsHide:true});child.stdout.pipe(log);child.stderr.pipe(log);child.on('error',error=>resolve({ok:false,message:`Medya işleyici başlatılamadı: ${error.message}`,logPath}));child.on('close',code=>resolve(code===0?{ok:true,message:`Batch tamamlandı. Çıktı: ${root}`,logPath}:{ok:false,message:`Batch hata koduyla durdu: ${code}. Günlük: ${logPath}`,logPath}))})});

app.whenReady().then(()=>{createWindow();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow()})});app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
