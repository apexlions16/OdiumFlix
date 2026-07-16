# OdiumFlix medya yayın hattı

## Kaynak
- Ana arşiv dosyası MKV olarak Hugging Face üzerinde saklanabilir.
- MKV içindeki video, çoklu ses ve altyazı parçaları FFmpeg/FFprobe ile analiz edilir.
- Kaynak dosya doğrudan tarayıcıya verilmez; uyumluluk ve adaptive bitrate için yayın paketleri üretilir.

## Yayın çıktısı
- HLS master playlist (`master.m3u8`)
- Her mevcut kalite için ayrı video rendition: 2160p, 1440/1080p+, 1080p, 720p, 480p
- Her dil/rol için ayrı ses rendition
- WebVTT veya IMSC1 altyazı rendition'ları
- CMAF/fMP4 parçaları

Bir kalite kaynakta yoksa playlist'e eklenmez. Player yalnızca mevcut varyantları gösterir. `AUTO` modu bant genişliği ve buffer durumuna göre kaliteyi otomatik seçer; kullanıcı dilerse belirli kaliteyi kilitler.

## Gelecek servisler
1. Studio yükleme oturumu oluşturur.
2. Kaynak Hugging Face'e yüklenir.
3. İş kuyruğu medya dönüştürme görevi başlatır.
4. FFprobe parça metadatasını çıkarır.
5. FFmpeg kalite merdiveni ve ses parçalarını üretir.
6. Paketleyici HLS manifestlerini oluşturur.
7. Katalog manifesti GitHub/veritabanında yayınlanır.
8. İstemciler yalnızca katalog API'si ve signed/controlled medya URL'lerini kullanır.
