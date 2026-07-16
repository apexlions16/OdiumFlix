# OdiumFlix v0.3.0-alpha.1

Bu sürüm sahte katalog içeriğini kaldırır ve gerçek yerel medya işleme/yükleme akışını kullanıma açar.

## Android düzeltmesi

Önceki Android paketi geliştirme amaçlı `assembleDebug` APK idi ve tek başına açıldığında Metro geliştirme sunucusu arayabiliyordu. Bu sürümde hem izleyici hem Studio APK, JavaScript bundle'ı içine gömülmüş `assembleRelease` paketi olarak üretilir. Expo SDK 57 ile eşleşen React sürümü de `19.2.3` olarak sabitlenmiştir.

## Yerel medya işleme

- MKV önce Windows bilgisayarda analiz edilir ve seçilen işleme modeline göre yerelde hazırlanır.
- `Otomatik`: Ses veya altyazısı olmayan MKV doğrudan yüklenebilir; diğer içerikler ayrılır.
- `Yerelde ayır`: Video kaliteleri, ortak ses havuzu ve altyazılar ayrı dosyalara hazırlanır.
- `Doğrudan`: Kaynak dosya dönüştürülmeden eklenir.
- “Orijinal dosyayı sakla” kapalıysa kaynak MKV Hugging Face'e yüklenmez.
- Hazır 4K, 1080p, 720p gibi dosyalar aynı başlık altında tek asset olur ve yalnız bir ortak ses/altyazı setini kullanır.

## Kodekler

Video hedefleri: otomatik, H.264, H.265/HEVC, AV1, VP9 ve uygun hazırlanmış kalite dosyalarında stream-copy.

Ses hedefleri: kaynak kodeğini koru, AAC, MP3, AC-3, E-AC-3, Opus, Vorbis, FLAC, ALAC, PCM 16-bit ve PCM 24-bit. “Kaynak kodeğini koru” DTS, TrueHD ve FFmpeg'in okuyabildiği diğer sesleri de dönüştürmeden saklamayı dener.

## Altyazılar

Gömülü ve harici SRT, VTT, ASS, SSA, SUB/IDX, SUP, STL, TTML/DFXP, SMI/SAMI ve FFmpeg'in okuyabildiği diğer formatlar kabul edilir. WebVTT dönüşümü mümkünse oynatma sürümü oluşturulur; özgün dosya ayrıca korunur.

## Hugging Face ve katalog

- Studio içinde Hugging Face repo kimliği, write token, repo türü (`dataset`, `model`, `space`) ve özel/açık seçimi bulunur.
- Repo yoksa worker otomatik oluşturmayı dener.
- Xet yüksek performans modu kullanılır.
- Klasör başına sabit güvenlik sınırı 9000 dosyadır.
- Yaklaşık 100 dosyaya kadar tek commit, daha büyük batch'lerde güvenli commit grupları kullanılır.
- Gerçek asset bilgileri GitHub `catalog/media/index.json` kataloğuna yazılır.

## Metadata

IMDb bağlantısındaki `tt...` kimliği alınır. TMDB Read Access Token kullanılarak başlık, açıklama, yayın tarihi, türler, oyuncular, ekip, poster, arka plan ve uygun resmi YouTube fragmanı çekilir. IMDb sayfası kazınmaz.

## Alpha notları

- Tokenlar pakete gömülmez.
- Windows paketleri ticari kod imzasına sahip değildir; SmartScreen uyarısı görülebilir.
- Android release APK test anahtarıyla imzalanır ve mağaza yayını için uygun değildir.
- Gerçek bir içeriği oynatma testi, kullanıcının HF reposu/tokenı ve örnek medya ile sonraki test adımıdır.
