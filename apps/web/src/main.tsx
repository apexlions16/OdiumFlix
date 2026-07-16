import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import Hls from 'hls.js';
import {Bell, ChevronDown, Info, ListPlus, Play, Search, X} from 'lucide-react';
import {loadCatalog, type ContentItem} from '@odiumflix/catalog';
import './styles.css';
import './player.css';

const App = () => {
  const [catalog, setCatalog] = useState<ContentItem[]>([]);
  const [selected, setSelected] = useState<ContentItem | null>(null);
  const [playing, setPlaying] = useState<ContentItem | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);

  const reload = async () => {
    setLoading(true);
    setError('');
    try {
      setCatalog(await loadCatalog());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  const requestPlay = (item: ContentItem) => {
    if (!item.playbackUrl) {
      setNotice(item.playbackError || 'Bu içerik için oynatılabilir bir kaynak bulunamadı.');
      return;
    }
    setSelected(null);
    setPlaying(item);
  };

  const hero = catalog[0];
  const results = useMemo(
    () => catalog.filter(item => `${item.title} ${item.genres.join(' ')}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr'))),
    [catalog, query],
  );
  const rows = useMemo(() => {
    if (!catalog.length) return [];
    const episodes = catalog.filter(item => item.source.contentType === 'episode');
    const movies = catalog.filter(item => item.source.contentType !== 'episode');
    return [
      {title: 'Yeni Eklenenler', items: catalog},
      {title: 'Filmler', items: movies},
      {title: 'Dizi Bölümleri', items: episodes},
    ].filter(row => row.items.length);
  }, [catalog]);

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">O</span><span>ODIUMFLIX</span></div>
      <nav><a className="active">Ana Sayfa</a><a>Filmler</a><a>Diziler</a></nav>
      <div className="top-actions">
        <label className={`search ${query ? 'expanded' : ''}`}><Search size={18}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Başlık, tür..."/></label>
        <button aria-label="Bildirimler"><Bell size={19}/></button>
        <button className="avatar" onClick={() => setProfileOpen(!profileOpen)}>KA</button>
        <ChevronDown size={16}/>
      </div>
      {profileOpen && <div className="profile-menu"><strong>Kerem Aslı</strong><span>OdiumFlix Alpha</span></div>}
    </header>

    {loading && <EmptyState title="Katalog yükleniyor" copy="GitHub kataloğu kontrol ediliyor…" busy/>}
    {!loading && error && <EmptyState title="Katalog bağlantısı kurulamadı" copy={error} action={reload}/>}
    {!loading && !error && !catalog.length && <EmptyState title="Henüz içerik yok" copy="OdiumFlix Studio’dan ilk içeriği yüklediğinde katalog burada otomatik oluşacak."/>}

    {!loading && !error && catalog.length > 0 && (query ? (
      <main className="search-page">
        <h1>“{query}” için sonuçlar</h1>
        <div className="search-grid">{results.map(item => <PosterCard key={item.id} item={item} onOpen={() => setSelected(item)} onPlay={() => requestPlay(item)}/>)}</div>
      </main>
    ) : <>
      <section className="hero" style={{'--hero-image': `url(${hero.backdrop || hero.poster || ''})`} as React.CSSProperties}>
        <div className="hero-vignette"/>
        <div className="hero-content">
          <p className="eyebrow">{hero.eyebrow}</p>
          <h1>{hero.title}</h1>
          <div className="meta">
            {hero.year && <span>{hero.year}</span>}
            <span>{hero.duration}</span>
            {hero.qualities[0] && <span className="quality">{hero.qualities[0].name}</span>}
          </div>
          <p className="hero-copy">{hero.description}</p>
          <div className="hero-buttons">
            <button className="primary" onClick={() => requestPlay(hero)}><Play fill="currentColor"/>Oynat</button>
            <button onClick={() => setSelected(hero)}><Info/>Bilgiler</button>
            {hero.trailerUrl && <button onClick={() => window.open(hero.trailerUrl!, '_blank', 'noopener')}><Play/>Fragman</button>}
            <button className="circle"><ListPlus/></button>
          </div>
          {hero.playbackError && <p className="playback-warning">{hero.playbackError}</p>}
        </div>
      </section>
      <main className="content-rows">
        {rows.map(row => <ContentRow key={row.title} title={row.title} items={row.items} onOpen={setSelected} onPlay={requestPlay}/>) }
      </main>
    </>)}

    {selected && <DetailModal item={selected} onClose={() => setSelected(null)} onPlay={() => requestPlay(selected)}/>} 
    {playing && <PlayerScreen item={playing} onClose={() => setPlaying(null)}/>} 
    {notice && <div className="app-notice"><span>{notice}</span><button onClick={() => setNotice('')}><X size={18}/></button></div>}
  </div>;
};

const EmptyState = ({title, copy, action, busy}:{title:string;copy:string;action?:()=>void;busy?:boolean}) =>
  <main style={{minHeight:'100vh',display:'grid',placeItems:'center',padding:'100px 24px'}}>
    <section style={{width:'min(680px,94vw)',padding:'52px',border:'1px solid #ffffff14',borderRadius:24,background:'#111116',textAlign:'center'}}>
      <div style={{fontSize:48,color:'#ff365f',marginBottom:12}}>{busy ? '◌' : '＋'}</div>
      <h1 style={{margin:'0 0 12px'}}>{title}</h1>
      <p style={{color:'#92929f',lineHeight:1.7}}>{copy}</p>
      {action && <button onClick={action} style={{marginTop:18,border:0,borderRadius:11,padding:'12px 18px',fontWeight:800}}>Tekrar dene</button>}
    </section>
  </main>;

const ContentRow = ({title, items, onOpen, onPlay}:{title:string;items:ContentItem[];onOpen:(item:ContentItem)=>void;onPlay:(item:ContentItem)=>void}) =>
  <section className="row-section">
    <div className="row-heading"><h2>{title}</h2></div>
    <div className="rail-wrap"><div className="rail">{items.map(item => <PosterCard key={item.id} item={item} onOpen={() => onOpen(item)} onPlay={() => onPlay(item)}/>)}</div></div>
  </section>;

const PosterCard = ({item, onOpen, onPlay}:{item:ContentItem;onOpen:()=>void;onPlay:()=>void}) =>
  <article className="poster-card" onClick={onOpen}>
    {item.backdrop || item.poster ? <img src={item.backdrop || item.poster} alt={item.title}/> : null}
    <div className="card-overlay" style={{opacity:1}}>
      <button aria-label={`${item.title} oynat`} onClick={event => {event.stopPropagation(); onPlay();}}><Play size={17} fill="currentColor"/></button>
      <div><b>{item.title}</b><small>{item.playbackUrl ? item.duration : 'Oynatma paketi eksik'}</small></div>
    </div>
  </article>;

const DetailModal = ({item, onClose, onPlay}:{item:ContentItem;onClose:()=>void;onPlay:()=>void}) =>
  <div className="modal-backdrop" onMouseDown={event => {if (event.target === event.currentTarget) onClose();}}>
    <article className="detail-modal">
      <button className="close" onClick={onClose}><X/></button>
      <div className="detail-hero" style={{'--detail-image': `url(${item.backdrop || item.poster || ''})`} as React.CSSProperties}>
        <div className="detail-shade"/>
        <div className="detail-title"><p>{item.eyebrow}</p><h2>{item.title}</h2></div>
      </div>
      <div className="detail-body">
        <div>
          <div className="meta">{item.year && <span>{item.year}</span>}<span>{item.duration}</span></div>
          <p>{item.description}</p>
          <div className="detail-actions">
            <button className="primary" onClick={onPlay}><Play fill="currentColor"/>Oynat</button>
            {item.trailerUrl && <button onClick={() => window.open(item.trailerUrl!, '_blank', 'noopener')}><Play/>Fragmanı aç</button>}
          </div>
          {item.playbackError && <p className="playback-warning">{item.playbackError}</p>}
        </div>
        <aside>
          <p><span>Türler:</span> {item.genres.join(', ') || 'Belirtilmedi'}</p>
          <p><span>Ses:</span> {item.audio.map(track => `${track.name}${track.codec ? ` (${track.codec})` : ''}`).join(', ') || 'Sessiz'}</p>
          <p><span>Altyazı:</span> {item.subtitles.map(track => track.name).join(', ') || 'Yok'}</p>
          <p><span>Oynatma:</span> {item.playbackMode === 'hls' ? 'Uyarlanabilir HLS' : item.playbackMode === 'direct' ? 'Doğrudan dosya' : 'Hazır değil'}</p>
        </aside>
      </div>
      <div className="availability"><strong>Mevcut kaliteler</strong>{item.qualities.map(quality => <span key={quality.name}>{quality.name}</span>)}</div>
    </article>
  </div>;

const PlayerScreen = ({item, onClose}:{item:ContentItem;onClose:()=>void}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playerError, setPlayerError] = useState('');

  useEffect(() => {
    const video = videoRef.current;
    const url = item.playbackUrl;
    if (!video || !url) return;
    setPlayerError('');
    let hls: Hls | undefined;

    const start = () => video.play().catch(() => undefined);
    if (item.playbackMode === 'hls' && Hls.isSupported()) {
      hls = new Hls({enableWorker:true, lowLatencyMode:false, backBufferLength:90});
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, start);
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) return;
        setPlayerError(`Akış açılamadı: ${data.details}`);
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls?.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls?.recoverMediaError();
        else hls?.destroy();
      });
    } else if (item.playbackMode === 'hls' && video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      video.addEventListener('loadedmetadata', start, {once:true});
    } else {
      video.src = url;
      video.addEventListener('loadedmetadata', start, {once:true});
    }

    return () => {
      hls?.destroy();
      video.pause();
      video.removeAttribute('src');
      video.load();
    };
  }, [item]);

  return <div className="real-player">
    <video ref={videoRef} controls playsInline autoPlay crossOrigin="anonymous" poster={item.backdrop || item.poster}/>
    <div className="real-player-top">
      <button onClick={onClose}><X/></button>
      <div><strong>{item.title}</strong><small>{item.qualities.map(value => value.name).join(' · ')}</small></div>
    </div>
    {playerError && <div className="player-error"><strong>Oynatma hatası</strong><span>{playerError}</span><small>Yeni Studio ile içeriği tekrar HLS olarak yüklediğinden emin ol.</small></div>}
  </div>;
};

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
