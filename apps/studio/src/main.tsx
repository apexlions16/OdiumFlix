import React, {useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {
  CloudUpload, Database, FileAudio, FileText, FileVideo,
  FolderOpen, HardDrive, KeyRound, Link2, LoaderCircle, Plus, Settings,
  ShieldCheck, Trash2, WandSparkles, X,
} from 'lucide-react';
import './styles.css';
import './media.css';

type Quality = '2160p'|'1440p'|'1080p+'|'1080p'|'720p'|'480p';
type ContentType = 'movie'|'short'|'episode'|'documentary';
type ProcessingMode = 'auto'|'split'|'direct';
type RepoType = 'dataset'|'model'|'space';
type AudioCodec = 'copy'|'aac'|'mp3'|'ac3'|'eac3'|'opus'|'vorbis'|'flac'|'alac'|'pcm_s16le'|'pcm_s24le';

type PickedFile = {name:string;path?:string;size:number};
type Attachment = PickedFile & {id:string};

type BatchRow = {
  id:string;
  fileName:string;
  localPath?:string;
  size:number;
  title:string;
  type:ContentType;
  sourceQuality:Quality;
  targets:Quality[]; // old worker compatibility; always contains only sourceQuality
  imdbUrl:string;
  season?:number;
  episode?:number;
  processingMode:ProcessingMode;
  keepOriginal:boolean;
  videoCodec:'copy';
  audioCodec:AudioCodec;
  externalAudio:Attachment[];
  externalSubtitles:Attachment[];
};

type BatchSettings = {
  hfRepo:string;
  hfRepoType:RepoType;
  hfPrivate:boolean;
  hfToken:string;
  githubRepo:string;
  githubToken:string;
  githubBranch:string;
  tmdbToken:string;
  metadataLanguage:string;
  outputDir?:string;
};

type MetadataResult = {
  title?:string;
  type?:string;
  overview?:string;
  releaseDate?:string;
  runtime?:number;
  genres?:string[];
  cast?:Array<{name?:string;character?:string}>;
  trailerUrl?:string;
};

type StudioBridge = {
  selectMedia:()=>Promise<PickedFile[]>;
  selectAudio:()=>Promise<PickedFile[]>;
  selectSubtitles:()=>Promise<PickedFile[]>;
  startBatch:(payload:{rows:BatchRow[];settings:BatchSettings})=>Promise<{ok:boolean;message:string;logPath?:string}>;
  fetchMetadata:(payload:{imdbUrl:string;tmdbToken:string;language:string})=>Promise<{ok:boolean;message:string;metadata?:MetadataResult}>;
};

declare global { interface Window { odiumStudio?: StudioBridge } }

const qualities: Quality[] = ['2160p','1440p','1080p+','1080p','720p','480p'];
const audioCodecs: AudioCodec[] = ['copy','aac','mp3','ac3','eac3','opus','vorbis','flac','alac','pcm_s16le','pcm_s24le'];
const uid = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;

const inferQuality = (name:string):Quality =>
  /2160|4k/i.test(name) ? '2160p' :
  /1440/i.test(name) ? '1440p' :
  /1080.*plus|fhd\+/i.test(name) ? '1080p+' :
  /1080|fhd/i.test(name) ? '1080p' :
  /720|hd/i.test(name) ? '720p' : '480p';

const cleanTitle = (name:string) => name
  .replace(/\.[^.]+$/, '')
  .replace(/\b(2160p|1440p|1080p\+?|720p|480p|4k|fhd\+?|web-?dl|bluray|x26[45]|hevc|av1)\b/gi, ' ')
  .replace(/[._-]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const prettyBytes = (size:number) =>
  size > 1024 ** 3 ? `${(size / 1024 ** 3).toFixed(1)} GB` :
  size > 1024 ** 2 ? `${(size / 1024 ** 2).toFixed(1)} MB` :
  `${Math.ceil(size / 1024)} KB`;

const App = () => {
  const browserMedia = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [settings, setSettings] = useState<BatchSettings>({
    hfRepo:'', hfRepoType:'dataset', hfPrivate:false, hfToken:'',
    githubRepo:'apexlions16/OdiumFlix', githubToken:'', githubBranch:'main',
    tmdbToken:'', metadataLanguage:'tr-TR',
  });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(true);

  const estimatedFiles = useMemo(
    () => rows.reduce((total,row) => {
      const videoFiles = row.processingMode === 'direct' ? 1 : 3;
      const audioFiles = Math.max(1,row.externalAudio.length + 1) * 2;
      const subtitleFiles = row.externalSubtitles.length * 3;
      return total + videoFiles + audioFiles + subtitleFiles + 4;
    },0),
    [rows],
  );

  const addMedia = (files:PickedFile[]) => {
    setRows(current => [
      ...current,
      ...files.map(file => {
        const sourceQuality=inferQuality(file.name);
        return {
          id:uid(), fileName:file.name, localPath:file.path, size:file.size,
          title:cleanTitle(file.name), type:'movie' as ContentType,
          sourceQuality, targets:[sourceQuality], imdbUrl:'',
          processingMode:'auto' as ProcessingMode, keepOriginal:false,
          videoCodec:'copy' as const, audioCodec:'copy' as AudioCodec,
          externalAudio:[], externalSubtitles:[],
        };
      }),
    ]);
  };

  const selectMedia = async () => {
    if(window.odiumStudio)addMedia(await window.odiumStudio.selectMedia());
    else browserMedia.current?.click();
  };

  const patch = (id:string,value:Partial<BatchRow>) =>
    setRows(current=>current.map(row=>row.id===id?{...row,...value}:row));

  const attach = async (row:BatchRow,kind:'audio'|'subtitles') => {
    if(!window.odiumStudio){setResult('Harici ses ve altyazı seçimi Windows Studio içinde kullanılabilir.');return;}
    const files=kind==='audio'?await window.odiumStudio.selectAudio():await window.odiumStudio.selectSubtitles();
    const attachments=files.map(file=>({...file,id:uid()}));
    patch(row.id,kind==='audio'
      ?{externalAudio:[...row.externalAudio,...attachments]}
      :{externalSubtitles:[...row.externalSubtitles,...attachments]});
  };

  const removeAttachment = (row:BatchRow,kind:'audio'|'subtitles',attachmentId:string) =>
    patch(row.id,kind==='audio'
      ?{externalAudio:row.externalAudio.filter(file=>file.id!==attachmentId)}
      :{externalSubtitles:row.externalSubtitles.filter(file=>file.id!==attachmentId)});

  const fetchMetadata = async (row:BatchRow) => {
    if(!row.imdbUrl)return setResult('Önce IMDb bağlantısını yapıştır.');
    if(!settings.tmdbToken)return setResult('TMDB API Read Access Token veya v3 API Key gir.');
    if(!window.odiumStudio)return setResult('IMDb metadata önizlemesi Windows Studio içinde çalışır.');
    setBusy(true);
    try{
      const answer=await window.odiumStudio.fetchMetadata({imdbUrl:row.imdbUrl,tmdbToken:settings.tmdbToken,language:settings.metadataLanguage});
      if(!answer.ok||!answer.metadata)throw new Error(answer.message);
      patch(row.id,{title:answer.metadata.title||row.title,type:answer.metadata.type==='tv'?'episode':row.type});
      setResult(`${answer.metadata.title||row.title} metadata bilgileri alındı.`);
    }catch(reason){setResult(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const exportPlan = () => {
    const payload={schemaVersion:3,settings,rows};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='odiumflix-lossless-batch-v3.json';anchor.click();URL.revokeObjectURL(url);
  };

  const startBatch = async () => {
    if(!rows.length)return;
    if(!settings.hfRepo||!settings.hfToken){setSettingsOpen(true);setResult('Hugging Face repo kimliği ve yazma tokenı zorunlu.');return;}
    setBusy(true);setResult('');
    try{
      if(!window.odiumStudio){exportPlan();setResult('Batch planı indirildi. Gerçek yerel işleme için Windows Studio EXE sürümünü kullan.');return;}
      const answer=await window.odiumStudio.startBatch({rows,settings});
      if(!answer.ok)throw new Error(answer.message);
      setResult(answer.message);
    }catch(reason){setResult(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <div className="media-shell">
    <aside className="media-sidebar">
      <div className="logo"><span>O</span><div>ODIUMFLIX<small>STUDIO 0.3 α2</small></div></div>
      <button className="side-active"><CloudUpload/>İçerik yükleme</button>
      <button onClick={()=>setSettingsOpen(!settingsOpen)}><Settings/>Bağlantılar</button>
      <div className="side-note"><ShieldCheck/><span>Video kalite politikası</span><strong>Kayıpsız kopya</strong></div>
      <div className="side-note"><ShieldCheck/><span>Klasör başına sınır</span><strong>9000 dosya</strong></div>
    </aside>

    <main className="media-main">
      <header className="media-header">
        <div><p>YEREL MEDYA MERKEZİ</p><h1>Kaliteyi değiştirmeden yükle</h1><span>Seçtiğin kalite yalnız etikettir. Video yeniden kodlanmaz, küçültülmez veya bitrate’i düşürülmez.</span></div>
        <button className="media-primary" onClick={selectMedia}><Plus/>Kaynak ekle</button>
      </header>

      {settingsOpen&&<section className="connection-grid">
        <ConnectionCard icon={<HardDrive/>} title="Hugging Face">
          <label>Repo kimliği<input value={settings.hfRepo} onChange={event=>setSettings({...settings,hfRepo:event.target.value})} placeholder="kullanici/odiumflix-media"/></label>
          <div className="field-row">
            <label>Repo türü<select value={settings.hfRepoType} onChange={event=>setSettings({...settings,hfRepoType:event.target.value as RepoType})}><option value="dataset">Dataset</option><option value="model">Model</option><option value="space">Space</option></select></label>
            <label className="check-field"><input type="checkbox" checked={settings.hfPrivate} onChange={event=>setSettings({...settings,hfPrivate:event.target.checked})}/>Özel repo</label>
          </div>
          <label>Write token<input type="password" value={settings.hfToken} onChange={event=>setSettings({...settings,hfToken:event.target.value})} placeholder="hf_..."/></label>
        </ConnectionCard>

        <ConnectionCard icon={<Database/>} title="GitHub katalog">
          <label>Repository<input value={settings.githubRepo} onChange={event=>setSettings({...settings,githubRepo:event.target.value})}/></label>
          <label>Branch<input value={settings.githubBranch} onChange={event=>setSettings({...settings,githubBranch:event.target.value})}/></label>
          <label>Fine-grained token<input type="password" value={settings.githubToken} onChange={event=>setSettings({...settings,githubToken:event.target.value})} placeholder="github_pat_..."/></label>
        </ConnectionCard>

        <ConnectionCard icon={<Link2/>} title="IMDb / TMDB metadata">
          <label>Read Access Token veya v3 API Key<input type="password" value={settings.tmdbToken} onChange={event=>setSettings({...settings,tmdbToken:event.target.value})} placeholder="eyJ... veya 32 karakter API key"/></label>
          <label>Dil<select value={settings.metadataLanguage} onChange={event=>setSettings({...settings,metadataLanguage:event.target.value})}><option value="tr-TR">Türkçe</option><option value="en-US">English</option></select></label>
          <p><code>Bearer </code> yazısını ekleme. Geçersiz anahtar metadata’yı atlatır; medya yüklemesini durdurmaz.</p>
        </ConnectionCard>
      </section>}

      <section className="batch-summary">
        <div><strong>{rows.length}</strong><span>yüklenen kalite dosyası</span></div>
        <div><strong>{estimatedFiles}</strong><span>tahmini çıktı</span></div>
        <div><strong>{Math.max(0,Math.ceil(estimatedFiles/100))}</strong><span>HF commit</span></div>
        <div><strong>0×</strong><span>video yeniden kodlama</span></div>
      </section>

      {!rows.length?<section className="catalog-empty" onClick={selectMedia}>
        <FolderOpen size={52}/><h2>İlk gerçek içeriği ekle</h2>
        <p>MKV, MP4 veya önceden hazırladığın kalite dosyalarını seç. Her dosya seçtiğin kalite etiketiyle aynen korunur.</p>
        <button className="media-primary"><CloudUpload/>Dosyaları seç</button>
      </section>:<section className="media-list">
        {rows.map(row=><article className="media-card" key={row.id}>
          <div className="media-card-head">
            <FileVideo/><div><input className="title-input" value={row.title} onChange={event=>patch(row.id,{title:event.target.value})}/><small>{row.fileName} · {prettyBytes(row.size)}</small></div>
            <button className="icon-danger" onClick={()=>setRows(current=>current.filter(value=>value.id!==row.id))}><Trash2/></button>
          </div>

          <div className="media-fields">
            <label>İçerik türü<select value={row.type} onChange={event=>patch(row.id,{type:event.target.value as ContentType})}><option value="movie">Film</option><option value="short">Kısa film</option><option value="episode">Dizi bölümü</option><option value="documentary">Belgesel</option></select></label>
            <label>İşleme<select value={row.processingMode} onChange={event=>patch(row.id,{processingMode:event.target.value as ProcessingMode})}><option value="auto">Otomatik · sessiz dosya doğrudan</option><option value="split">Video/ses/altyazıyı kayıpsız ayır</option><option value="direct">Dosyayı aynen yükle</option></select></label>
            <label>Kalite etiketi<select value={row.sourceQuality} onChange={event=>{const quality=event.target.value as Quality;patch(row.id,{sourceQuality:quality,targets:[quality]});}}>{qualities.map(quality=><option key={quality}>{quality}</option>)}</select></label>
            <label>Video politikası<input readOnly value="Stream copy · ölçekleme yok"/></label>
            <label>Ses kodeği<select value={row.audioCodec} onChange={event=>patch(row.id,{audioCodec:event.target.value as AudioCodec})}>{audioCodecs.map(codec=><option key={codec} value={codec}>{codec==='copy'?'Kaynak kodeğini aynen koru':codec}</option>)}</select></label>
            <label className="check-field"><input type="checkbox" checked={row.keepOriginal} onChange={event=>patch(row.id,{keepOriginal:event.target.checked})}/>Orijinal kapsayıcıyı da sakla</label>
          </div>

          <div className="quality-block">
            <strong>{row.sourceQuality} etiketiyle kayıpsız paketlenecek</strong>
            <p>Gerçek çözünürlük ve kodek ffprobe ile ayrıca kaydedilir. Etiket çözünürlüğü değiştirmez.</p>
          </div>

          <div className="imdb-row"><Link2/><input value={row.imdbUrl} onChange={event=>patch(row.id,{imdbUrl:event.target.value})} placeholder="https://www.imdb.com/title/tt1234567/"/><button onClick={()=>fetchMetadata(row)} disabled={busy}><WandSparkles/>Metadata getir</button></div>
          {row.type==='episode'&&<div className="episode-row"><label>Sezon<input type="number" min="1" value={row.season||''} onChange={event=>patch(row.id,{season:Number(event.target.value)||undefined})}/></label><label>Bölüm<input type="number" min="1" value={row.episode||''} onChange={event=>patch(row.id,{episode:Number(event.target.value)||undefined})}/></label></div>}

          <div className="attachments">
            <AttachmentPanel icon={<FileAudio/>} title="Ortak ses dosyaları" files={row.externalAudio} onAdd={()=>attach(row,'audio')} onRemove={id=>removeAttachment(row,'audio',id)} copy="Tüm kalite dosyaları bu tek ses setini kullanır; varsayılan olarak kaynak kodek korunur."/>
            <AttachmentPanel icon={<FileText/>} title="Harici altyazılar" files={row.externalSubtitles} onAdd={()=>attach(row,'subtitles')} onRemove={id=>removeAttachment(row,'subtitles',id)} copy="SRT, VTT, ASS, SSA, SUB, SUP, STL, TTML ve FFmpeg’in okuyabildiği diğer formatlar."/>
          </div>
        </article>)}
      </section>}

      {result&&<div className="media-result">{result}<button onClick={()=>setResult('')}><X/></button></div>}
      <footer className="media-footer">
        <div><KeyRound/><span>Tokenlar release içine gömülmez. Video akışı hiçbir koşulda yeniden kodlanmaz.</span></div>
        <button className="media-primary" disabled={!rows.length||busy} onClick={startBatch}>{busy?<><LoaderCircle className="spin"/>İşleniyor</>:<><CloudUpload/>Kayıpsız işle ve yükle</>}</button>
      </footer>

      <input ref={browserMedia} hidden type="file" multiple accept=".mkv,.mp4,.mov,.m4v,.webm,.avi,.ts,.m2ts" onChange={event=>{const files=Array.from(event.target.files||[]).map(file=>({name:file.name,size:file.size}));addMedia(files);event.currentTarget.value='';}}/>
    </main>
  </div>;
};

const ConnectionCard = ({icon,title,children}:{icon:React.ReactNode;title:string;children:React.ReactNode}) =>
  <section className="connection-card"><header>{icon}<h3>{title}</h3></header>{children}</section>;

const AttachmentPanel = ({icon,title,files,onAdd,onRemove,copy}:{icon:React.ReactNode;title:string;files:Attachment[];onAdd:()=>void;onRemove:(id:string)=>void;copy:string}) =>
  <section className="attachment-panel"><header>{icon}<div><strong>{title}</strong><small>{copy}</small></div><button onClick={onAdd}><Plus/>Ekle</button></header>{files.length>0&&<div className="attachment-files">{files.map(file=><span key={file.id}>{file.name}<button onClick={()=>onRemove(file.id)}><X/></button></span>)}</div>}</section>;

createRoot(document.getElementById('root')!).render(<App/>);
