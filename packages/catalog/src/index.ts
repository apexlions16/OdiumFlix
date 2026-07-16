export type CatalogTrack = {
  id: string;
  language?: string;
  name: string;
  codec?: string;
  sourceCodec?: string;
  channels?: number | null;
  default?: boolean;
  forced?: boolean;
  playlist?: string;
  file?: string;
  originalFile?: string;
  format?: string;
};

export type CatalogQuality = {
  name: string;
  width?: number | null;
  height?: number | null;
  bandwidth?: number;
  codec?: string;
  playlist?: string;
  file?: string;
};

export type CatalogMetadata = {
  provider?: string;
  tmdbId?: number;
  imdbId?: string;
  type?: string;
  title?: string;
  originalTitle?: string;
  overview?: string;
  releaseDate?: string;
  runtime?: number | null;
  genres?: string[];
  tagline?: string;
  status?: string;
  cast?: Array<{name?: string; character?: string; profilePath?: string}>;
  crew?: Array<{name?: string; job?: string; department?: string}>;
  trailerUrl?: string | null;
};

export type CatalogAsset = {
  schemaVersion: number;
  assetId: string;
  title: string;
  contentType: string;
  durationSeconds?: number;
  externalIds?: {imdb?: string | null; tmdb?: number | null};
  episode?: {season?: number; number?: number} | null;
  metadata?: CatalogMetadata | null;
  artwork?: {poster?: string; backdrop?: string};
  playback: {
    mode: 'hls' | 'direct';
    master?: string | null;
    directFile?: string | null;
    qualities: CatalogQuality[];
    audio: CatalogTrack[];
    subtitles: CatalogTrack[];
  };
  storage?: {
    provider: 'huggingface';
    repoId: string;
    repoType: 'dataset' | 'model' | 'space';
    revision?: string;
    baseUrl: string;
    private?: boolean;
  };
  createdAt?: number;
};

export type CatalogDocument = {
  schemaVersion: number;
  assets: Record<string, CatalogAsset>;
};

export type ContentItem = {
  id: string;
  title: string;
  eyebrow: string;
  description: string;
  year?: number;
  duration: string;
  genres: string[];
  poster?: string;
  backdrop?: string;
  trailerUrl?: string | null;
  audio: CatalogTrack[];
  subtitles: CatalogTrack[];
  qualities: CatalogQuality[];
  playbackUrl?: string;
  playbackMode: 'hls' | 'direct';
  source: CatalogAsset;
};

export const DEFAULT_CATALOG_URL =
  'https://raw.githubusercontent.com/apexlions16/OdiumFlix/main/catalog/media/index.json';

const joinUrl = (base: string, ...parts: Array<string | null | undefined>) =>
  [base.replace(/\/+$/, ''), ...parts.filter(Boolean).map(part => String(part).replace(/^\/+|\/+$/g, ''))].join('/');

export const assetUrl = (asset: CatalogAsset, relative?: string | null): string | undefined => {
  if (!relative || !asset.storage?.baseUrl) return undefined;
  return joinUrl(asset.storage.baseUrl, 'objects', asset.assetId.slice(0, 2), asset.assetId, relative);
};

export const toContentItem = (asset: CatalogAsset): ContentItem => {
  const metadata = asset.metadata || {};
  const release = metadata.releaseDate ? new Date(metadata.releaseDate) : null;
  const year = release && !Number.isNaN(release.getTime()) ? release.getUTCFullYear() : undefined;
  const durationSeconds = asset.durationSeconds || ((metadata.runtime || 0) * 60);
  const duration = durationSeconds
    ? `${Math.max(1, Math.round(durationSeconds / 60))} dk`
    : 'Süre bilinmiyor';
  const playbackRelative = asset.playback.mode === 'hls'
    ? asset.playback.master
    : asset.playback.directFile;
  return {
    id: asset.assetId,
    title: metadata.title || asset.title,
    eyebrow: asset.contentType === 'episode' ? 'DİZİ BÖLÜMÜ' : 'ODIUMFLIX',
    description: metadata.overview || 'Açıklama henüz eklenmedi.',
    year,
    duration,
    genres: metadata.genres || [],
    poster: assetUrl(asset, asset.artwork?.poster),
    backdrop: assetUrl(asset, asset.artwork?.backdrop),
    trailerUrl: metadata.trailerUrl,
    audio: asset.playback.audio || [],
    subtitles: asset.playback.subtitles || [],
    qualities: asset.playback.qualities || [],
    playbackUrl: assetUrl(asset, playbackRelative),
    playbackMode: asset.playback.mode,
    source: asset,
  };
};

export async function loadCatalog(url = DEFAULT_CATALOG_URL): Promise<ContentItem[]> {
  const response = await fetch(url, {cache: 'no-store'});
  if (!response.ok) throw new Error(`Katalog alınamadı (${response.status})`);
  const document = await response.json() as CatalogDocument;
  if (!document || typeof document.assets !== 'object') return [];
  return Object.values(document.assets)
    .map(toContentItem)
    .sort((a, b) => (b.source.createdAt || 0) - (a.source.createdAt || 0));
}

export const catalog: ContentItem[] = [];
export const rows: Array<{title: string; ids: string[]}> = [];
