# OdiumFlix v0.3.0-alpha.3

Bu sürüm MKV yükleme, katalog şeması ve gerçek oynatma akışını birlikte düzeltir.

## Oynatma düzeltmeleri

- Windows ve web izleyiciye gerçek `hls.js` video oynatıcısı eklendi.
- Android izleyiciye `expo-video` tabanlı gerçek HLS oynatıcı eklendi.
- Eski düz katalog kayıtları artık uygulamayı çökertmez; eksik alanlar güvenli biçimde normalize edilir.
- Katalog artık tam `playback`, `storage`, `assetId`, `durationSeconds`, `artwork` ve `hfPath` bilgilerini saklar.
- Özel Hugging Face deposu doğrudan istemcide oynatılamadığında açık bir hata gösterilir.

## MKV ve HLS işleme

- Otomatik mod sessiz MKV dosyasını artık yalnız MKV olarak bırakmaz.
- Önerilen mod her yüklenen kalite için video bitstream'ini değiştirmeden HLS üretir.
- Video yeniden ölçeklenmez, bitrate düşürülmez ve yeniden kodlanmaz.
- Önce fMP4 HLS denenir; kapsayıcı uymazsa MPEG-TS HLS stream-copy denenir.
- Her ikisi de mümkün değilse kaliteyi değiştirmek yerine video-only MKV fallback korunur ve katalog açık uyarı taşır.

## Yeni dosya adları

- Ana oynatma listesi: `playback.m3u8`
- Kalite oynatma listesi: `video.m3u8`
- fMP4 medya dosyası: `video.m4s`
- fMP4 başlangıç dosyası: `video-init.mp4`
- MPEG-TS fallback parçaları: `video-00000.ts`, `video-00001.ts`, ...
- Ses oynatma listesi: `audio.m3u8`
- Altyazı oynatma listesi: `subtitles.m3u8`

## Mevcut bozuk yükleme

Alpha.2 ile yalnız MKV olarak yüklenmiş içerik, uzaktan kendiliğinden HLS'ye dönüşmez. Aynı IMDb bağlantısı veya aynı içerik kimliğiyle alpha.3 Studio üzerinden yeniden yükleme yapılmalıdır. Yeni yükleme eski bozuk katalog kaydının yerini otomatik alır.

Doğrudan istemci oynatması için Hugging Face medya deposu public olmalıdır. Private depo kullanılacaksa daha sonra kimlik doğrulamalı medya gateway'i gerekir; token uygulama içine gömülmez.
