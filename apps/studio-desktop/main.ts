import {app, BrowserWindow, dialog, ipcMain, shell} from 'electron';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';
import ffprobeStatic from 'ffprobe-static';

type Attachment = {id:string;name:string;path?:string;size:number};
type Row = {
  localPath?:string; fileName:string; title:string; type:string;
  sourceQuality:string; targets?:string[]; imdbUrl?:string; season?:number; episode?:number;
  processingMode:'auto'|'split'|'direct'; keepOriginal:boolean; videoCodec?:string; audioCodec:string;
  externalAudio:Attachment[]; externalSubtitles:Attachment[];
};
type Settings = {
  hfRepo:string; hfRepoType:'dataset'|'model'|'space'; hfPrivate:boolean; hfToken:string;
  githubRepo:string; githubToken:string; githubBranch:string; tmdbToken:string;
  metadataLanguage:string; outputDir?:string;
};
type Payload = {rows:Row[];settings:Settings};

const qualityOrder = ['2160p','1440p','1080p+','1080p','720p','480p'];

const createWindow = () => {
  const win = new BrowserWindow({
    width:1500, height:940, minWidth:1050, minHeight:700,
    backgroundColor:'#08080c', title:'OdiumFlix Studio',
    webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false},
  });
  if (!app.isPackaged) win.loadURL('http://localhost:5174');
  else win.loadFile(path.join(process.resourcesPath,'studio','index.html'));
  win.webContents.setWindowOpenHandler(({url}) => {shell.openExternal(url);return {action:'deny'};});
};

const pickFiles = async (name:string, extensions:string[]) => {
  const result = await dialog.showOpenDialog({properties:['openFile','multiSelections'],filters:[{name,extensions}]});
  if (result.canceled) return [];
  return result.filePaths.map(file => ({name:path.basename(file),path:file,size:fs.statSync(file).size}));
};

ipcMain.handle('studio:select-media', () => pickFiles('Video',['mkv','mp4','mov','m4v','webm','avi','ts','m2ts']));
ipcMain.handle('studio:select-audio', () => pickFiles('Ses',['aac','m4a','mp3','mp2','ac3','eac3','ec3','opus','ogg','flac','wav','mka','dts','thd','mlp','alac','aiff','wv','ape','tak','tta']));
ipcMain.handle('studio:select-subtitles', () => pickFiles('Altyazı',['srt','vtt','ass','ssa','sub','idx','sup','stl','ttml','dfxp','smi','sami','txt','mks']));

const workerCommand = () => {
  if (app.isPackaged) {
    const executable = path.join(process.resourcesPath,'worker',process.platform === 'win32' ? 'odium-media.exe' : 'odium-media');
    if (fs.existsSync(executable)) return {cmd:executable,args:[] as string[]};
    throw new Error(`Paketlenmiş medya worker bulunamadı: ${executable}`);
  }
  const script = path.resolve(__dirname,'../../../tools/media_pipeline/odium_media.py');
  return {cmd:process.platform === 'win32' ? 'py' : 'python3',args:process.platform === 'win32' ? ['-3',script] : [script]};
};

const firstExisting = (values:Array<string|false|null|undefined>) => values.find((value):value is string=>Boolean(value&&fs.existsSync(value)));

const unpackedModulePath = (value:string|false|null|undefined) => {
  if (!value) return undefined;
  return value.replace(`${path.sep}app.asar${path.sep}`,`${path.sep}app.asar.unpacked${path.sep}`);
};

const mediaTools = () => {
  const packagedFfmpeg = process.platform === 'win32' ? path.join(process.resourcesPath,'media-tools','ffmpeg.exe') : path.join(process.resourcesPath,'media-tools','ffmpeg');
  const packagedFfprobe = process.platform === 'win32' ? path.join(process.resourcesPath,'media-tools','ffprobe.exe') : path.join(process.resourcesPath,'media-tools','ffprobe');
  const ffmpeg = firstExisting([
    app.isPackaged && packagedFfmpeg,
    unpackedModulePath(ffmpegPath),
    typeof ffmpegPath === 'string' ? ffmpegPath : undefined,
  ]) || (!app.isPackaged ? 'ffmpeg' : undefined);
  const ffprobe = firstExisting([
    app.isPackaged && packagedFfprobe,
    unpackedModulePath(ffprobeStatic.path),
    ffprobeStatic.path,
  ]) || (!app.isPackaged ? 'ffprobe' : undefined);
  if (!ffmpeg || !ffprobe) {
    throw new Error(
      `FFmpeg/ffprobe paket içinde bulunamadı. ffmpeg=${ffmpeg||'YOK'}, ffprobe=${ffprobe||'YOK'}. `+
      'OdiumFlix Studio alpha.2 veya daha yeni sürümü temiz kur.'
    );
  }
  return {ffmpeg,ffprobe};
};

const toBatchItems = (rows:Row[]) => {
  const grouped = new Map<string,any>();
  for (const row of rows) {
    if (!row.localPath) throw new Error(`${row.fileName} için yerel dosya yolu bulunamadı.`);
    const key = `${row.title.trim().toLocaleLowerCase('tr')}|${row.type}|${row.season||0}|${row.episode||0}`;
    const current = grouped.get(key);
    const audio = row.externalAudio.map(file=>file.path).filter((value):value is string=>Boolean(value));
    const subtitles = row.externalSubtitles.map(file=>file.path).filter((value):value is string=>Boolean(value));
    if (!current) {
      grouped.set(key,{
        source:row.localPath,title:row.title,content_type:row.type,source_quality:row.sourceQuality,
        target_qualities:[row.sourceQuality],imdb_url:row.imdbUrl||undefined,season:row.season,episode:row.episode,
        processing_mode:row.processingMode,keep_original:row.keepOriginal,video_codec:'copy',
        audio_codec:row.audioCodec||'copy',external_audio:audio,external_subtitles:subtitles,
        prepared_variants:{[row.sourceQuality]:row.localPath},
      });
      continue;
    }
    current.prepared_variants[row.sourceQuality] = row.localPath;
    current.target_qualities = Object.keys(current.prepared_variants);
    current.external_audio = [...new Set([...current.external_audio,...audio])];
    current.external_subtitles = [...new Set([...current.external_subtitles,...subtitles])];
    current.keep_original = current.keep_original || row.keepOriginal;
    if (!current.imdb_url && row.imdbUrl) current.imdb_url = row.imdbUrl;
    const currentIndex = qualityOrder.indexOf(current.source_quality);
    const newIndex = qualityOrder.indexOf(row.sourceQuality);
    if (newIndex !== -1 && (currentIndex === -1 || newIndex < currentIndex)) {
      current.source = row.localPath;
      current.source_quality = row.sourceQuality;
    }
  }
  return [...grouped.values()];
};

const workerEnvironment = (settings?:Partial<Settings>) => {
  const tools = mediaTools();
  return {
    ...process.env,
    HF_TOKEN:settings?.hfToken||process.env.HF_TOKEN,
    GITHUB_TOKEN:settings?.githubToken||process.env.GITHUB_TOKEN,
    TMDB_API_TOKEN:settings?.tmdbToken||process.env.TMDB_API_TOKEN,
    HF_XET_HIGH_PERFORMANCE:'1',
    PYTHONUTF8:'1',
    PYTHONIOENCODING:'utf-8',
    ODIUM_FFMPEG:tools.ffmpeg,
    ODIUM_FFPROBE:tools.ffprobe,
  };
};

const executeWorker = (args:string[],settings?:Partial<Settings>,logPath?:string):Promise<{code:number;stdout:string;stderr:string}> => new Promise(resolve => {
  let worker:{cmd:string;args:string[]};
  let env:NodeJS.ProcessEnv;
  try {
    worker=workerCommand();
    env=workerEnvironment(settings);
  } catch (reason) {
    resolve({code:-1,stdout:'',stderr:reason instanceof Error?reason.message:String(reason)});
    return;
  }
  const child=spawn(worker.cmd,[...worker.args,...args],{env,windowsHide:true});
  let stdout='';let stderr='';const log=logPath?fs.createWriteStream(logPath,{flags:'a'}):null;
  child.stdout.on('data',chunk=>{const text=Buffer.from(chunk).toString('utf8');stdout+=text;log?.write(text);});
  child.stderr.on('data',chunk=>{const text=Buffer.from(chunk).toString('utf8');stderr+=text;log?.write(text);});
  child.on('error',error=>{log?.end();resolve({code:-1,stdout,stderr:`${stderr}\n${error.message}`});});
  child.on('close',code=>{log?.end();resolve({code:code??-1,stdout,stderr});});
});

ipcMain.handle('studio:fetch-metadata', async (_event,payload:{imdbUrl:string;tmdbToken:string;language:string}) => {
  const result=await executeWorker(['metadata','--imdb-url',payload.imdbUrl,'--token',payload.tmdbToken,'--language',payload.language||'tr-TR'],{tmdbToken:payload.tmdbToken});
  if(result.code!==0)return{ok:false,message:result.stderr.trim()||'Metadata alınamadı.'};
  try{return{ok:true,message:'Metadata alındı.',metadata:JSON.parse(result.stdout)};}
  catch{return{ok:false,message:`Metadata çıktısı okunamadı: ${result.stdout.slice(0,500)}`};}
});

ipcMain.handle('studio:start-batch',async(_event,payload:Payload)=>{
  if(!payload.rows.length)return{ok:false,message:'Batch boş.'};
  if(!payload.settings.hfRepo||!payload.settings.hfToken)return{ok:false,message:'Hugging Face repo kimliği ve write token zorunlu.'};
  let items:any[];
  try{items=toBatchItems(payload.rows);}catch(reason){return{ok:false,message:reason instanceof Error?reason.message:String(reason)};}
  const runId=new Date().toISOString().replace(/[:.]/g,'-');
  const base=payload.settings.outputDir||path.join(app.getPath('videos'),'OdiumFlix','processed');
  const output=path.join(base,`run-${runId}`);fs.mkdirSync(output,{recursive:true});
  const configPath=path.join(app.getPath('temp'),`odiumflix-batch-${runId}.json`);
  const logPath=path.join(app.getPath('logs'),`odiumflix-media-${runId}.log`);
  fs.writeFileSync(configPath,JSON.stringify({schemaVersion:3,items},null,2),'utf8');

  const diagnostics=await executeWorker(['diagnostics'],payload.settings,logPath);
  if(diagnostics.code!==0)return{ok:false,message:`Medya araçları doğrulanamadı. ${diagnostics.stderr.trim()}\nGünlük: ${logPath}`,logPath};

  const args=['batch',configPath,'--output',output,'--hf-repo',payload.settings.hfRepo,'--hf-repo-type',payload.settings.hfRepoType,'--message',`OdiumFlix Studio lossless batch ${new Date().toISOString()}`,'--metadata-language',payload.settings.metadataLanguage||'tr-TR','--overwrite'];
  if(payload.settings.hfPrivate)args.push('--hf-private');
  if(payload.settings.githubRepo&&payload.settings.githubToken)args.push('--github-repo',payload.settings.githubRepo,'--github-branch',payload.settings.githubBranch||'main');
  if(payload.settings.tmdbToken)args.push('--tmdb-token',payload.settings.tmdbToken);
  const result=await executeWorker(args,payload.settings,logPath);
  if(result.code!==0)return{ok:false,message:`Batch durdu. ${result.stderr.trim()||`Hata kodu: ${result.code}`}\nGünlük: ${logPath}`,logPath};
  let warning='';
  try{const data=JSON.parse(result.stdout);if(data.warnings?.length)warning=`\nUyarılar:\n- ${data.warnings.join('\n- ')}`;}catch{}
  return{ok:true,message:`Batch tamamlandı. Yerel çıktı: ${output}${warning}`,logPath};
});

app.whenReady().then(()=>{createWindow();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow();});});
app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit();});
