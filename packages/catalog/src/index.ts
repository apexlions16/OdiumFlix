export type ContentItem = {
  id: string;
  title: string;
  eyebrow: string;
  description: string;
  year: number;
  duration: string;
  rating: string;
  match: number;
  genres: string[];
  poster: string;
  backdrop: string;
  progress?: number;
  badge?: string;
  audio: string[];
  subtitles: string[];
  qualities: string[];
};

export const catalog: ContentItem[] = [
  {
    id: 'last-light', title: 'Son Işık', eyebrow: 'ODIUMFLIX ORİJİNAL',
    description: 'Şehrin elektrikleri sonsuza dek kesildiğinde, genç bir görüntü yönetmeni elindeki son çalışan kamerayla insanlığın son gecesini kaydetmeye karar verir.',
    year: 2026, duration: '24 dk', rating: '13+', match: 98,
    genres: ['Bilim Kurgu', 'Dram', 'Gizem'], poster: 'art/last-light-poster.svg', backdrop: 'art/last-light-wide.svg',
    progress: 42, badge: 'Yeni', audio: ['Türkçe 5.1', 'English 5.1', 'Türkçe Sesli Betimleme'], subtitles: ['Türkçe', 'English', 'Türkçe SDH'], qualities: ['4K', 'FHD+', '1080p', '720p', '480p']
  },
  {
    id: 'echo-room', title: 'Yankı Odası', eyebrow: 'KISA FİLM',
    description: 'Bir ses mühendisi, yıllar önce kaybettiği kardeşinin sesini terk edilmiş bir stüdyoda yeniden duyar.',
    year: 2025, duration: '18 dk', rating: '16+', match: 95,
    genres: ['Gerilim', 'Psikolojik'], poster: 'art/echo-room-poster.svg', backdrop: 'art/echo-room-wide.svg',
    audio: ['Türkçe Stereo', 'English Stereo'], subtitles: ['Türkçe', 'English'], qualities: ['4K', '1080p', '720p', '480p']
  },
  {
    id: 'red-frequency', title: 'Kırmızı Frekans', eyebrow: 'ODIUMFLIX ORİJİNAL',
    description: 'Gece radyosunda duyulan tek bir frekans, dinleyen herkesin aynı rüyayı görmesine neden olur.',
    year: 2026, duration: '31 dk', rating: '16+', match: 93,
    genres: ['Korku', 'Gizem'], poster: 'art/red-frequency-poster.svg', backdrop: 'art/red-frequency-wide.svg',
    badge: 'Çok Yakında', audio: ['Türkçe 5.1'], subtitles: ['Türkçe', 'English'], qualities: ['4K', '1080p']
  },
  {
    id: 'blue-hour', title: 'Mavi Saat', eyebrow: 'FESTİVAL SEÇKİSİ',
    description: 'Gün doğmadan önceki bir saat boyunca iki yabancının yolları, boş bir sahil kasabasında kesişir.',
    year: 2024, duration: '22 dk', rating: '7+', match: 91,
    genres: ['Romantik', 'Dram'], poster: 'art/blue-hour-poster.svg', backdrop: 'art/blue-hour-wide.svg',
    audio: ['Türkçe Stereo'], subtitles: ['Türkçe', 'English', 'Deutsch'], qualities: ['1080p', '720p', '480p']
  },
  {
    id: 'fracture', title: 'Kırılma', eyebrow: 'KISA FİLM',
    description: 'Tek bir kararın beş farklı hayata yayılan sonuçları, parçalı bir anlatıyla birleşir.',
    year: 2025, duration: '27 dk', rating: '13+', match: 89,
    genres: ['Dram', 'Deneysel'], poster: 'art/fracture-poster.svg', backdrop: 'art/fracture-wide.svg',
    progress: 76, audio: ['Türkçe 5.1'], subtitles: ['Türkçe', 'English'], qualities: ['4K', 'FHD+', '1080p', '720p']
  },
  {
    id: 'after-rain', title: 'Yağmurdan Sonra', eyebrow: 'BELGESEL',
    description: 'Bir kasabanın değişen iklimle mücadelesini, üç kuşağın gözünden anlatan kısa belgesel.',
    year: 2023, duration: '35 dk', rating: 'Genel İzleyici', match: 87,
    genres: ['Belgesel', 'Doğa'], poster: 'art/after-rain-poster.svg', backdrop: 'art/after-rain-wide.svg',
    audio: ['Türkçe Stereo', 'English Stereo'], subtitles: ['Türkçe', 'English', 'Français'], qualities: ['1080p', '720p', '480p']
  }
];

export const rows = [
  { title: 'İzlemeye Devam Et', ids: ['last-light', 'fracture'] },
  { title: 'OdiumFlix Orijinalleri', ids: ['last-light', 'red-frequency', 'echo-room', 'blue-hour'] },
  { title: 'Festival Seçkisi', ids: ['blue-hour', 'after-rain', 'fracture', 'echo-room'] },
  { title: 'Kısa ve Etkileyici', ids: ['echo-room', 'last-light', 'blue-hour', 'fracture', 'red-frequency'] }
];
