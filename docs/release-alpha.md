# v0.2.0-alpha.1 test kapsamı

Bu alpha sürümü arayüz ve gerçek yerel medya işleme altyapısını birleştirir.

## Çalışan parçalar

- Studio web: çoklu dosya seçimi, dosya başına kaynak kalite, hedef kalite, içerik türü ve IMDb kimliği.
- Windows Studio: yerel dosya yolu seçimi, batch planı oluşturma ve paketlenmiş `odium-media` worker'ını çalıştırma.
- Media worker: MKV track analizi, çoklu ses, altyazı, single-file CMAF/HLS kalite çıktıları, 9000 dosya kontrolü, Xet tabanlı HF batch commit ve GitHub katalog commit'i.
- Mobil Studio: birden fazla dosya seçimi, kalite planı ve Windows/LAN worker API'sine multipart stream.
- İzleyici web/mobil/masaüstü: önceki arayüz prototipi.

## Alpha sınırlamaları

- Hugging Face ve GitHub tokenları kullanıcı tarafından girilmelidir; release içinde token bulunmaz.
- Metadata için `TMDB_API_TOKEN` gerekir.
- Windows güvenlik imzası henüz yoktur; SmartScreen uyarısı görülebilir.
- Android APK debug/test paketidir.
- Gerçek prod ortamında mobil worker endpoint'i TLS ve kimlik doğrulama ile korunmalıdır.
