import React, {useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Bell, ChevronDown, ChevronLeft, ChevronRight, Info, ListPlus, Maximize, Pause, Play, Search, Settings, SkipBack, SkipForward, Subtitles, Volume2, X} from 'lucide-react';
import {catalog, rows, type ContentItem} from '@odiumflix/catalog';
import './styles.css';

const App = () => {
  const [selected, setSelected] = useState<ContentItem | null>(null);
  const [playing, setPlaying] = useState<ContentItem | null>(null);
  const [query, setQuery] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const hero = catalog[0];
  const results = useMemo(() => catalog.filter(item => `${item.title} ${item.genres.join(' ')}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr'))), [query]);

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">O</span><span>ODIUMFLIX</span></div>
      <nav><a className="active">Ana Sayfa</a><a>Filmler</a><a>Kısa Filmler</a><a>Listem</a></nav>
      <div className="top-actions">
        <label className={`search ${query ? 'expanded' : ''}`}><Search size={18}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Başlık, tür..."/></label>
        <button aria-label="Bildirimler"><Bell size={19}/><i/></button>
        <button className="avatar" onClick={()=>setProfileOpen(!profileOpen)}>KA</button>
        <ChevronDown size={16}/>
      </div>
      {profileOpen && <div className="profile-menu"><strong>Kerem Aslı</strong><span>Profilleri yönet</span><span>Hesap</span><span>Yardım merkezi</span></div>}
    </header>

    {query ? <main className="search-page"><h1>“{query}” için sonuçlar</h1><div className="search-grid">{results.map(item=><PosterCard key={item.id} item={item} onOpen={()=>setSelected(item)}/>)}</div></main> : <>
      <section className="hero" style={{'--hero-image': `url(${hero.backdrop})`} as React.CSSProperties}>
        <div className="hero-vignette"/><div className="hero-content">
          <p className="eyebrow">{hero.eyebrow}</p><h1>{hero.title}</h1>
          <div className="meta"><strong>%{hero.match} Eşleşme</strong><span>{hero.year}</span><span className="rating">{hero.rating}</span><span>{hero.duration}</span><span className="quality">4K</span></div>
          <p className="hero-copy">{hero.description}</p>
          <div className="hero-buttons"><button className="primary" onClick={()=>setPlaying(hero)}><Play fill="currentColor"/>Oynat</button><button onClick={()=>setSelected(hero)}><Info/>Daha Fazla Bilgi</button><button className="circle"><ListPlus/></button></div>
        </div>
        <div className="hero-sound"><Volume2/></div>
      </section>
      <main className="content-rows">{rows.map(row => <ContentRow key={row.title} title={row.title} items={row.ids.map(id=>catalog.find(c=>c.id===id)!).filter(Boolean)} onOpen={setSelected}/>)}</main>
    </>}

    {selected && <DetailModal item={selected} onClose={()=>setSelected(null)} onPlay={()=>{setSelected(null);setPlaying(selected)}}/>}
    {playing && <Player item={playing} onClose={()=>setPlaying(null)}/>} 
  </div>
}

const ContentRow = ({title, items, onOpen}:{title:string;items:ContentItem[];onOpen:(i:ContentItem)=>void}) => {
  const [offset,setOffset]=useState(0);
  return <section className="row-section"><div className="row-heading"><h2>{title}</h2><span>Tümünü Gör <ChevronRight size={15}/></span></div>
    <div className="rail-wrap"><button className="rail-arrow left" onClick={()=>setOffset(Math.max(0,offset-1))}><ChevronLeft/></button><div className="rail" style={{transform:`translateX(-${offset*18}vw)`}}>{items.map(item=><PosterCard key={item.id} item={item} onOpen={()=>onOpen(item)}/>)}</div><button className="rail-arrow right" onClick={()=>setOffset(Math.min(Math.max(0,items.length-4),offset+1))}><ChevronRight/></button></div>
  </section>
}

const PosterCard = ({item,onOpen}:{item:ContentItem;onOpen:()=>void}) => <article className="poster-card" onClick={onOpen}>
  <img src={item.poster} alt={item.title}/>{item.badge&&<span className="badge">{item.badge}</span>}
  <div className="card-overlay"><button><Play size={17} fill="currentColor"/></button><div><b>{item.title}</b><small>%{item.match} eşleşme · {item.duration}</small></div></div>
  {item.progress !== undefined && <div className="progress"><i style={{width:`${item.progress}%`}}/></div>}
</article>

const DetailModal = ({item,onClose,onPlay}:{item:ContentItem;onClose:()=>void;onPlay:()=>void}) => <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><article className="detail-modal">
  <button className="close" onClick={onClose}><X/></button><div className="detail-hero" style={{'--detail-image':`url(${item.backdrop})`} as React.CSSProperties}><div className="detail-shade"/><div className="detail-title"><p>{item.eyebrow}</p><h2>{item.title}</h2><div><button className="primary" onClick={onPlay}><Play fill="currentColor"/>Oynat</button><button className="circle"><ListPlus/></button></div></div></div>
  <div className="detail-body"><div><div className="meta"><strong>%{item.match} Eşleşme</strong><span>{item.year}</span><span className="rating">{item.rating}</span><span>{item.duration}</span><span className="quality">{item.qualities[0]}</span></div><p>{item.description}</p></div><aside><p><span>Türler:</span> {item.genres.join(', ')}</p><p><span>Ses:</span> {item.audio.join(', ')}</p><p><span>Altyazı:</span> {item.subtitles.join(', ')}</p></aside></div>
  <div className="availability"><strong>Mevcut kaliteler</strong>{item.qualities.map(q=><span key={q}>{q}</span>)}</div>
</article></div>

const Player = ({item,onClose}:{item:ContentItem;onClose:()=>void}) => {
  const [paused,setPaused]=useState(false); const [settings,setSettings]=useState(false); const [trackMenu,setTrackMenu]=useState(false); const [quality,setQuality]=useState('Otomatik');
  return <div className="player-screen" style={{'--player-image':`url(${item.backdrop})`} as React.CSSProperties}>
    <div className="player-top"><button onClick={onClose}><ChevronLeft/></button><div><small>Şimdi oynatılıyor</small><strong>{item.title}</strong></div></div>
    <button className="big-play" onClick={()=>setPaused(!paused)}>{paused?<Play fill="currentColor"/>:<Pause fill="currentColor"/>}</button>
    <div className="player-bottom"><div className="timeline"><i/><span/></div><div className="control-row"><div><button onClick={()=>setPaused(!paused)}>{paused?<Play fill="currentColor"/>:<Pause fill="currentColor"/>}</button><button><SkipBack/></button><button><SkipForward/></button><button><Volume2/></button><span>08:42 / {item.duration}</span></div><strong>{item.title}</strong><div><button onClick={()=>setTrackMenu(!trackMenu)}><Subtitles/></button><button onClick={()=>setSettings(!settings)}><Settings/></button><button><Maximize/></button></div></div></div>
    {trackMenu && <div className="player-menu tracks"><section><h3>Ses</h3>{item.audio.map((a,i)=><button className={i===0?'active':''} key={a}>{a}<span>{i===0?'✓':''}</span></button>)}</section><section><h3>Altyazı</h3><button className="active">Kapalı <span>✓</span></button>{item.subtitles.map(s=><button key={s}>{s}</button>)}</section></div>}
    {settings && <div className="player-menu settings"><h3>Video kalitesi</h3>{['Otomatik',...item.qualities].map(q=><button key={q} className={quality===q?'active':''} onClick={()=>{setQuality(q);setSettings(false)}}>{q}<span>{quality===q?'✓':''}</span></button>)}</div>}
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
