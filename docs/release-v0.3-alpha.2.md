# OdiumFlix v0.3.0-alpha.2

Bu sürüm içerik yükleme akışındaki üç kritik sorunu düzeltir.

## Düzeltilenler

- Windows Studio içinde `ffprobe.exe` artık `app.asar` yolundan değil, paketlenmiş `resources/media-tools` klasöründen çalıştırılır.
- Paketleme sırasında FFmpeg ve ffprobe dosyalarının gerçekten release içine girdiği CI tarafından doğrulanır.
- Windows Türkçe kod sayfasında metadata içinde `Ł`, `é`, `ß`, Japonca veya başka Unicode karakterleri olduğunda worker artık `UnicodeEncodeError` ile çökmez.
- TMDB alanı hem API Read Access Token (`eyJ...`) hem de 32 karakterli v3 API Key kabul eder.
- Geçersiz TMDB anahtarı içerik yüklemesini durdurmaz; metadata atlanır ve kullanıcıya anlaşılır uyarı verilir.

## Kayıpsız video politikası

- Seçtiğin kalite yalnız katalog etiketidir.
- Video hiçbir koşulda küçültülmez, ölçeklenmez, bitrate'i düşürülmez veya yeniden kodlanmaz.
- Hazır 2160p, 1080p, 720p gibi dosyalar yalnız stream-copy ile paketlenir.
- Eski “üretilecek alt kaliteler” ayarı yok sayılır; sadece gerçekten yüklediğin kalite dosyaları kullanılır.
- Kaynak çözünürlük ve kodek ayrıca ffprobe ile kaydedilir; kalite etiketi görüntüyü değiştirmez.
- HLS/fMP4 stream-copy mümkün değilse video yeniden kodlanmak yerine video-only MKV olarak kayıpsız korunur.

## Ses ve altyazı

- Varsayılan ses politikası kaynak kodeğini aynen korumaktır.
- AAC, MP3, AC-3, E-AC-3, Opus, Vorbis, FLAC, ALAC, PCM ve FFmpeg'in okuyabildiği diğer sesler MKA fallback ile korunabilir.
- Metin altyazılar WebVTT'ye dönüştürülür; özgün altyazı dosyası da korunur.

## Doğrulama

Release iş akışı şunları doğrular:

- Python worker sözdizimi
- Gerçek FFmpeg kayıpsız video hash testi
- Web ve Studio üretim build'leri
- Windows Worker ve Media Server EXE'leri
- Paketlenmiş Windows Studio içindeki FFmpeg/ffprobe dosyaları
- Windows izleyici
- Android izleyici release APK
- Android Studio release APK
