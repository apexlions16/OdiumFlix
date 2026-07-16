# OdiumFlix

Kısa filmler ve bağımsız yapımlar için çok platformlu, Netflix esintili fakat özgün görsel kimliğe sahip yayın platformu.

## Uygulamalar
- `apps/web`: İzleyici web uygulaması; katalog, arama, içerik detayı ve tam ekran player arayüzü.
- `apps/mobile`: Expo/React Native mobil istemcisi.
- `apps/desktop`: Electron masaüstü istemcisi; web deneyimini paketler.
- `apps/studio`: Web ve mobilde aynı yeteneklere taşınabilecek içerik yönetim panelinin web arayüzü.
- `packages/catalog`: Arayüz prototiplerinde kullanılan ortak katalog modeli.
- `packages/theme`: Ortak tasarım tokenları.

## Çalıştırma
```bash
npm install
npm run dev:web
npm run dev:studio
npm run dev:mobile
```

## Derleme
```bash
npm run build
```

## Medya yaklaşımı
MKV dosyaları arşiv kaynağı olarak tutulur. Web ve cihazlar arası yayın için içerik HLS/CMAF'e paketlenir; çoklu ses, altyazı, 4K–480p kalite varyantları, otomatik adaptive bitrate ve manuel kalite seçimi master playlist üzerinden sunulur. Ayrıntılar: `docs/media-pipeline.md`.

## Yol haritası
- Faz 1: Çok platformlu arayüz ve tasarım sistemi ✅
- Faz 2: Kimlik doğrulama, profil ve katalog API'si
- Faz 3: Hugging Face yükleme, FFmpeg iş kuyruğu ve HLS paketleme
- Faz 4: İzleme ilerlemesi, listeler, indirme ve bildirimler
- Faz 5: CI tabanlı web, Android, masaüstü ve Studio release'leri
