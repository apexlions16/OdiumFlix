# OdiumFlix

Kısa filmler ve bağımsız yapımlar için çok platformlu, Netflix esintili fakat özgün görsel kimliğe sahip yayın platformu.

## Uygulamalar

- `apps/web`: İzleyici web uygulaması; katalog, arama, içerik detayı ve player arayüzü.
- `apps/mobile`: Expo/React Native Android ve iOS izleyici istemcisi.
- `apps/desktop`: Electron masaüstü izleyici istemcisi.
- `apps/studio`: Web tabanlı OdiumFlix Studio ve batch yükleme arayüzü.
- `apps/studio-desktop`: Windows Studio; yerel MKV analizi, FFmpeg işleme ve Hugging Face/GitHub aktarımı.
- `apps/studio-mobile`: Mobil Studio; dosyaları Windows/LAN medya worker'ına stream eder.
- `tools/media_pipeline`: MKV analiz, HLS/CMAF üretim, Xet batch upload, metadata ve katalog worker'ı.
- `catalog/media`: GitHub üzerinde tutulan asset eşleştirme kataloğu.

## Medya yaklaşımı

Kaynak MKV arşiv girdisidir. `ffprobe` bütün video, ses ve altyazı parçalarını algılar. Yayın için 2160p, 1440p, 1080p+, 1080p, 720p ve 480p HLS/CMAF varyantları üretilebilir. Hazır kalite dosyaları aynı başlık ve bölüm altında tek asset olarak birleştirilebilir.

Video, alternatif sesler ve WebVTT altyazılar master HLS playlist üzerinden birlikte stream edilir. Mobil ve web istemcileri dosyaların tamamını önceden indirmez.

## Hugging Face düzeni

- Büyük medya dosyaları Xet üzerinden yüklenir.
- Dosya ve klasör isimleri opak `assetId` değerleridir.
- Gerçek başlık ve Hugging Face yolu `catalog/media/index.json` içinde eşleştirilir.
- Her klasör için OdiumFlix güvenlik sınırı 9000 dosyadır.
- Varsayılan batch üst sınırı 100 dosya işlemi/commit'tir; daha büyük işler güvenli commit gruplarına ayrılır.
- Single-file CMAF kullanılarak binlerce küçük segment yerine kalite veya ses başına birkaç büyük dosya oluşturulur.

Ayrıntılı yapı: `docs/media-storage-layout.md`.

## Yerel geliştirme

```bash
npm install
npm run dev:web
npm run dev:studio
npm run dev:mobile
npm run dev:studio-mobile
```

Medya motoru:

```bash
python -m pip install -r tools/media_pipeline/requirements.txt
python tools/media_pipeline/odium_media.py analyze "film.mkv"
python tools/media_pipeline/odium_media.py batch tools/media_pipeline/example-batch.json --output build/media --dry-run
```

Mobil Studio worker'ı:

```bash
python tools/media_pipeline/server.py --host 0.0.0.0 --port 8765
```

## Alpha release

`v0.2.0-alpha.1` iş akışı aşağıdaki test paketlerini üretir:

- Web izleyici ZIP
- Studio Web ZIP
- Windows izleyici kurucusu
- Windows Studio kurucu ve portable paket
- Windows medya worker/server araçları
- Android izleyici APK
- Android Studio APK

Bu alpha sürümünde tokenlar uygulamaya gömülmez. Hugging Face, GitHub ve TMDB erişimleri kullanıcı tarafından yapılandırılır.
