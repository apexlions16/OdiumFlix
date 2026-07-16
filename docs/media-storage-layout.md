# OdiumFlix medya depolama ve batch yükleme mimarisi

## Temel kararlar

- Kaynak MKV arşiv girdisidir. Web, Android ve masaüstü istemciler MKV'yi doğrudan indirmez.
- Oynatma çıktısı HLS/CMAF'tir. Video kaliteleri, ses parçaları ve WebVTT altyazılar master playlist üzerinden birlikte stream edilir.
- Her yapım veya bölüm için rastgele, anlamsız bir `assetId` üretilir. Hugging Face yolları insan tarafından okunabilir başlıklara bağlı değildir.
- Gerçek başlık, IMDb/TMDB kimliği, sezon-bölüm ve Hugging Face yolu GitHub'daki `catalog/media/index.json` dosyasında eşleştirilir.
- Xet kullanılır ve `HF_XET_HIGH_PERFORMANCE=1` etkinleştirilir.

## Hugging Face klasör yapısı

```text
objects/
  9e/
    9eefb4c26a194b1293759b67598d8f8f/
      asset.json
      master.m3u8
      video/
        2160p/{index.m3u8,init-2160p.mp4,stream.m4s}
        1080p/{index.m3u8,init-1080p.mp4,stream.m4s}
        720p/{index.m3u8,init-720p.mp4,stream.m4s}
        480p/{index.m3u8,init-480p.mp4,stream.m4s}
      audio/
        a00-tr/{index.m3u8,init-a00-tr.mp4,stream.m4s}
        a01-en/{index.m3u8,init-a01-en.mp4,stream.m4s}
      subtitles/
        s00-tr/{index.m3u8,captions.vtt}
```

İlk iki karakter üst seviye shard olarak kullanılır. Her asset kendi klasöründe kaldığı için tek bir dizinin bölümleri aynı klasörde birikmez.

## Dosya sınırları

- OdiumFlix güvenlik sınırı: klasör başına en fazla **9000 dosya**.
- İşleme tamamlandığında ve upload başlamadan önce bütün klasörler zorunlu olarak sayılır.
- Single-file CMAF sayesinde her kalite yaklaşık üç dosya, her ses parçası yaklaşık üç dosya üretir. Binlerce küçük HLS segmenti oluşmaz.
- Bir commit için varsayılan üst sınır **100 işlem**. 10–100 dosyalık bölüm tek commit gider. Daha büyük batch 100'lük güvenli commit gruplarına ayrılır.

## Batch işlemi

1. Kullanıcı bir veya birden fazla MKV/MP4/MOV seçer.
2. Her satırda kaynak kalite ve üretilecek hedef kaliteler ayrı seçilir.
3. `ffprobe` video, ses, altyazı, dil, kodek, kanal düzeni ve default/forced işaretlerini çıkarır.
4. Hazır kalite dosyası verilmişse o kalite için yeniden kaynak seçilebilir; eksik kaliteler ana kaynaktan dönüştürülür.
5. Bütün asset çıktıları yerel staging alanında hazırlanır.
6. Klasör başına 9000 sınırı kontrol edilir.
7. Hugging Face'e Xet ile, 100 dosyaya kadar tek commit olacak şekilde batch upload yapılır.
8. Başarılı HF commitlerinden sonra GitHub kataloğu tek commit ile güncellenir.

## Metadata

- IMDb kimliği girilirse TMDB `find` endpoint'i üzerinden eşleşme aranır.
- Başlıkla arama da desteklenir.
- Poster/backdrop dosyaları daha sonra Hugging Face `artwork/<assetId>/` altında tutulacaktır.
- IMDb sayfası kazınmaz. Resmî veya lisanslı veri sağlayıcıları dışında scraping kullanılmaz.

## Mobil Studio

Mobil Studio büyük videoyu cihazda 4K/1080p olarak dönüştürmez. Kaynak dosyayı kullanıcının Windows Studio medya worker'ına veya ileride kurulacak sunucu worker'ına stream eder. Böylece mobilde HF/GitHub yazma tokenı tutulmaz ve telefonun pil/ısı/bellek sınırları aşılmaz.
