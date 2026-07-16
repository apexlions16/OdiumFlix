# OdiumFlix

OdiumFlix, kullanıcının kendi film ve dizileri için yerel medya hazırlama, Hugging Face depolama ve çok platformlu izleme uygulamasıdır.

## Uygulamalar

- `apps/web`: Gerçek GitHub kataloğunu okuyan web izleyici.
- `apps/mobile`: Standalone release APK olarak derlenen Android izleyici.
- `apps/desktop`: Electron Windows izleyici.
- `apps/studio`: Hugging Face, GitHub ve metadata ayarlarını yöneten Studio arayüzü.
- `apps/studio-desktop`: MKV'leri yerelde ayıran ve yükleyen Windows Studio.
- `apps/studio-mobile`: Büyük dosyaları Windows/LAN worker'a aktaran mobil Studio.
- `tools/media_pipeline`: FFmpeg/ffprobe tabanlı medya işleyici ve FastAPI worker.

## Gerçek katalog

Mock içerik bulunmaz. `catalog/media/index.json` başlangıçta boştur. İlk başarılı Studio batch'inden sonra gerçek asset manifestleri buraya yazılır ve web/Android uygulamalarında görünür.

## Yerel medya akışı

1. MKV veya hazır kalite dosyaları Studio'ya eklenir.
2. Aynı başlık, tür, sezon ve bölüm numarasına sahip kalite dosyaları tek asset altında gruplanır.
3. Ana/yüksek kaliteli kaynak yalnız bir kez ses ve altyazı için analiz edilir.
4. Video kaliteleri ayrı hazırlanır; bütün kaliteler tek ortak ses ve altyazı havuzunu kullanır.
5. “Orijinali sakla” kapalıysa kaynak MKV yüklenmez.
6. Çıktılar klasör başına 9000 dosya sınırıyla doğrulanır.
7. Hugging Face Xet batch commitleri yapılır.
8. GitHub kataloğu güncellenir.

## İşleme modelleri

- `auto`: Sessiz ve altyazısız MKV doğrudan dosya olarak eklenebilir; diğerleri stream çıktısına ayrılır.
- `split`: Video, ses ve altyazılar yerelde ayrılır.
- `direct`: Kaynak video dönüştürülmeden yüklenir.

## Ses ve altyazı

Ses dönüştürme hedefleri: AAC, MP3, AC-3, E-AC-3, Opus, Vorbis, FLAC, ALAC, PCM16, PCM24 veya `copy`. `copy`, DTS/TrueHD dâhil kaynak kodeğini korumayı dener.

SRT, VTT, ASS, SSA, SUB, IDX, SUP, STL, TTML, DFXP, SMI, SAMI ve FFmpeg'in desteklediği diğer altyazılar kabul edilir. WebVTT oynatma çıktısı mümkün değilse özgün altyazı dosyası yine saklanır.

## Metadata

Studio'ya IMDb bağlantısı yapıştırılır. Bağlantıdaki IMDb kimliği, TMDB API üzerinden tam metadata, oyuncular, ekip, poster, backdrop ve fragman almak için kullanılır. `TMDB_API_TOKEN` veya Studio'daki TMDB Read Access Token alanı gereklidir.

## Android paketleme

Tek başına kurulabilen APK için:

```bash
cd apps/mobile
npx expo prebuild --platform android --no-install --clean
cd android
./gradlew assembleRelease
```

Debug APK release olarak yayımlanmaz; debug paket Metro geliştirme sunucusu gerektirebilir.

## Medya worker

```bash
python -m pip install -r tools/media_pipeline/requirements.txt
python tools/media_pipeline/odium_media.py analyze "film.mkv"
python tools/media_pipeline/odium_media.py batch tools/media_pipeline/example-batch.json \
  --output build/media \
  --hf-repo kullanici/odiumflix-media \
  --hf-repo-type dataset \
  --github-repo apexlions16/OdiumFlix
```

LAN worker:

```bash
python tools/media_pipeline/server.py --host 0.0.0.0 --port 8765
```
