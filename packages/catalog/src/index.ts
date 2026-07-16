export type CatalogTrack = {
  id: string;
  language?: string;
  name: string;
  codec?: string;
  sourceCodec?: string;
  channels?: number | null;
  default?: boolean;
  forced?: boolean;
  playlist?: string | null;
  file?: string | null;
  originalFile?: string | null;
  original?: string | null;
  format?: string;
};

export type CatalogQuality = {
  name: string;
  declaredQuality?: string;
  width?: number | null;
  height?: number | null;
  actualWidth?: number | null;
  actualHeight?: number | null;
  bandwidth?: number;
  bitRate?: number | null;
  codec?: string;
  playlist?: string | null;
  file?: string | null;
  packaging?: string;
  losslessCopy?: boolean;
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
  posterUrl?: string | null;
  backdropUrl?: string | null;
  cast?: Array<{name?: string; character?: string; profilePath?: string}>;
  crew?: Array<{name?: string; job?: string; department?: string}>;
  trailerUrl?: string | null;
};

export type CatalogPlayback = {
  mode: 'hls' | 'direct' | 'unavailable';
  master?: string | null;
  directFile?: string | null;
  qualities: CatalogQuality[];
  audio: CatalogTrack[];
  subtitles: CatalogTrack[];
};

export type CatalogStorage = {
  provider: 'huggingface';
  repoId: string;
  repoType: 'dataset' | 'model' | 'space';
  revision?: string;
  baseUrl: string;
  private?: boolean;
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
  artwork?: {poster?: string; backdrop?: string; posterUrl?: string; backdropUrl?: string};
  playback: CatalogPlayback;
  storage?: CatalogStorage;
  hfPath?: string;
  createdAt?: number;
  updatedAt?: number;
  warnings?: string[];
};

export type CatalogDocument = {
  schemaVersion: number;
  assets: Record<string, unknown>;
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
  playbackMode: 'hls' | 'direct' | 'unavailable';
  playbackError?: string;
  source: CatalogAsset;
};

export const DEFAULT_CATALOG_URL =
  'https://raw.githubusercontent.com/apexlions16/OdiumFlix/main/catalog/media/index.json';

const joinUrl = (base: string, ...parts: Array<string | null | undefined>) =>
  [base.replace(/\/+$/, ''), ...parts.filter(Boolean).map(part => String(part).replace(/^\/+|\/+$/g, ''))].join('/');

const array = <T>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];
const object = (value: unknown): Record<string, any> => value && typeof value === 'object' ? value as Record<string, any> : {};

export const normalizeCatalogAsset = (value: unknown, fallbackId: string): CatalogAsset => {
  const raw = object(value);
  const rawPlayback = object(raw.playback);
  const qualities = array<CatalogQuality>(rawPlayback.qualities ?? raw.qualities);
  const audio = array<CatalogTrack>(rawPlayback.audio ?? raw.audio);
  const subtitles = array<CatalogTrack>(rawPlayback.subtitles ?? raw.subtitles);
  const master = rawPlayback.master ?? raw.master ?? null;
  const explicitDirect = rawPlayback.directFile ?? raw.directFile ?? null;
  const qualityDirect = qualities.find(quality => quality.file)?.file ?? null;
  const directFile = explicitDirect || qualityDirect;
  const requestedMode = rawPlayback.mode;
  const mode: CatalogPlayback['mode'] = requestedMode === 'hls' || requestedMode === 'direct' || requestedMode === 'unavailable'
    ? requestedMode
    : master
      ? 'hls'
      : directFile
        ? 'direct'
        : 'unavailable';

  return {
    schemaVersion: Number(raw.schemaVersion || 2),
    assetId: String(raw.assetId || fallbackId),
    title: String(raw.title || raw.metadata?.title || 'Adsız içerik'),
    contentType: String(raw.contentType || 'movie'),
    durationSeconds: Number(raw.durationSeconds || 0) || undefined,
    externalIds: raw.externalIds,
    episode: raw.episode,
    metadata: raw.metadata || null,
    artwork: raw.artwork,
    playback: {mode, master, directFile, qualities, audio, subtitles},
    storage: raw.storage,
    hfPath: raw.hfPath,
    createdAt: Number(raw.createdAt || raw.updatedAt || 0) || undefined,
    updatedAt: Number(raw.updatedAt || 0) || undefined,
    warnings: array<string>(raw.warnings),
  };
};

export const assetUrl = (asset: CatalogAsset, relative?: string | null): string | undefined => {
  if (!relative || !asset.storage?.baseUrl) return undefined;
  const assetPath = asset.hfPath || `objects/${asset.assetId.slice(0, 2)}/${asset.assetId}`;
  return joinUrl(asset.storage.baseUrl, assetPath, relative);
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
  const privateStorage = asset.storage?.private === true;
  const playbackUrl = privateStorage ? undefined : assetUrl(asset, playbackRelative);
  const storageMissing = !asset.storage?.baseUrl;
  const sourceMissing = !playbackRelative;

  return {
    id: asset.assetId,
    title: metadata.title || asset.title,
    eyebrow: asset.contentType === 'episode' ? 'DİZİ BÖLÜMÜ' : 'ODIUMFLIX',
    description: metadata.overview || 'Açıklama henüz eklenmedi.',
    year,
    duration,
    genres: metadata.genres || [],
    poster: asset.artwork?.posterUrl || assetUrl(asset, asset.artwork?.poster) || metadata.posterUrl || undefined,
    backdrop: asset.artwork?.backdropUrl || assetUrl(asset, asset.artwork?.backdrop) || metadata.backdropUrl || undefined,
    trailerUrl: metadata.trailerUrl,
    audio: asset.playback.audio,
    subtitles: asset.playback.subtitles,
    qualities: asset.playback.qualities,
    playbackUrl,
    playbackMode: asset.playback.mode,
    playbackError: privateStorage
      ? 'Hugging Face deposu özel olduğu için izleyici token olmadan erişemez. Oynatma için public medya deposu kullan.'
      : storageMissing
      ? 'Bu eski katalog kaydında Hugging Face depo adresi yok. İçeriği yeni Studio ile yeniden yükle.'
      : sourceMissing
        ? 'Bu içerik için oynatma manifesti üretilmemiş. Yeni Studio ile HLS oynatma paketi oluştur.'
        : undefined,
    source: asset,
  };
};

export async function loadCatalog(url = DEFAULT_CATALOG_URL): Promise<ContentItem[]> {
  const separator = url.includes('?') ? '&' : '?';
  const response = await fetch(`${url}${separator}t=${Date.now()}`, {cache: 'no-store'});
  if (!response.ok) throw new Error(`Katalog alınamadı (${response.status})`);
  const document = await response.json() as CatalogDocument;
  if (!document || !document.assets || typeof document.assets !== 'object') return [];
  return Object.entries(document.assets)
    .map(([assetId, value]) => toContentItem(normalizeCatalogAsset(value, assetId)))
    .sort((a, b) => (b.source.createdAt || b.source.updatedAt || 0) - (a.source.createdAt || a.source.updatedAt || 0));
}

export const catalog: ContentItem[] = [];
export const rows: Array<{title: string; ids: string[]}> = [];
