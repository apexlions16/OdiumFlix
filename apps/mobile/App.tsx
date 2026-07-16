import React, {Component, type ReactNode, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  Modal,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

const CATALOG_URL =
  'https://raw.githubusercontent.com/apexlions16/OdiumFlix/main/catalog/media/index.json';

type Asset = {
  assetId: string;
  title: string;
  contentType: string;
  durationSeconds?: number;
  metadata?: {
    title?: string;
    overview?: string;
    releaseDate?: string;
    genres?: string[];
    trailerUrl?: string | null;
  } | null;
  artwork?: {poster?: string; backdrop?: string};
  playback?: {
    mode?: 'hls' | 'direct';
    master?: string | null;
    directFile?: string | null;
    qualities?: Array<{name: string}>;
    audio?: Array<{name: string; codec?: string}>;
    subtitles?: Array<{name: string; format?: string}>;
  };
  storage?: {baseUrl?: string};
};

type CatalogDocument = {assets?: Record<string, Asset>};
type Item = {
  id: string;
  title: string;
  description: string;
  year?: number;
  duration: string;
  genres: string[];
  poster?: string;
  backdrop?: string;
  trailer?: string | null;
  qualities: string[];
  audio: string[];
  subtitles: string[];
};

const join = (base: string, ...parts: Array<string | undefined>) =>
  [base.replace(/\/+$/, ''), ...parts.filter(Boolean).map(value => String(value).replace(/^\/+|\/+$/g, ''))].join('/');

const assetUrl = (asset: Asset, relative?: string) =>
  relative && asset.storage?.baseUrl
    ? join(asset.storage.baseUrl, 'objects', asset.assetId.slice(0, 2), asset.assetId, relative)
    : undefined;

const toItem = (asset: Asset): Item => {
  const date = asset.metadata?.releaseDate ? new Date(asset.metadata.releaseDate) : null;
  return {
    id: asset.assetId,
    title: asset.metadata?.title || asset.title,
    description: asset.metadata?.overview || 'Açıklama henüz eklenmedi.',
    year: date && !Number.isNaN(date.getTime()) ? date.getUTCFullYear() : undefined,
    duration: asset.durationSeconds ? `${Math.max(1, Math.round(asset.durationSeconds / 60))} dk` : 'Süre bilinmiyor',
    genres: asset.metadata?.genres || [],
    poster: assetUrl(asset, asset.artwork?.poster),
    backdrop: assetUrl(asset, asset.artwork?.backdrop),
    trailer: asset.metadata?.trailerUrl,
    qualities: (asset.playback?.qualities || []).map(value => value.name),
    audio: (asset.playback?.audio || []).map(value => `${value.name}${value.codec ? ` · ${value.codec}` : ''}`),
    subtitles: (asset.playback?.subtitles || []).map(value => `${value.name}${value.format ? ` · ${value.format}` : ''}`),
  };
};

class ErrorBoundary extends Component<{children: ReactNode}, {error?: string}> {
  state: {error?: string} = {};
  static getDerivedStateFromError(error: Error) {
    return {error: error.message || 'Bilinmeyen uygulama hatası'};
  }
  render() {
    if (this.state.error) {
      return (
        <SafeAreaView style={styles.root}>
          <View style={styles.center}>
            <Text style={styles.logo}>ODIUMFLIX</Text>
            <Text style={styles.errorTitle}>Uygulama açılamadı</Text>
            <Text style={styles.muted}>{this.state.error}</Text>
          </View>
        </SafeAreaView>
      );
    }
    return this.props.children;
  }
}

function OdiumFlixApp() {
  const [items, setItems] = useState<Item[]>([]);
  const [selected, setSelected] = useState<Item | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${CATALOG_URL}?t=${Date.now()}`);
      if (!response.ok) throw new Error(`Katalog alınamadı (${response.status})`);
      const document = (await response.json()) as CatalogDocument;
      const values = Object.values(document.assets || {}).map(toItem);
      setItems(values);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const hero = items[0];
  const sections = useMemo(() => {
    if (!items.length) return [];
    return [
      {title: 'Yeni Eklenenler', data: items},
      {title: 'Filmler ve Diziler', data: items.filter(item => item.id !== hero?.id)},
    ].filter(section => section.data.length);
  }, [items, hero?.id]);

  if (loading) {
    return (
      <SafeAreaView style={styles.root}>
        <StatusBar barStyle="light-content" />
        <View style={styles.center}>
          <Text style={styles.logo}>ODIUMFLIX</Text>
          <ActivityIndicator color="#ff365f" size="large" />
          <Text style={styles.muted}>Katalog yükleniyor…</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" />
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#ff365f" />}
        contentContainerStyle={styles.scroll}
      >
        <View style={styles.header}>
          <View style={styles.brandMark}><Text style={styles.brandMarkText}>O</Text></View>
          <Text style={styles.logo}>ODIUMFLIX</Text>
        </View>

        {error && (
          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>Katalog bağlantısı kurulamadı</Text>
            <Text style={styles.muted}>{error}</Text>
            <Pressable style={styles.secondaryButton} onPress={() => load()}>
              <Text style={styles.secondaryButtonText}>Tekrar dene</Text>
            </Pressable>
          </View>
        )}

        {!error && !items.length && (
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>＋</Text>
            <Text style={styles.emptyTitle}>Henüz içerik yok</Text>
            <Text style={styles.muted}>
              OdiumFlix Studio’dan ilk filmi veya diziyi yüklediğinde burada otomatik görünecek.
            </Text>
          </View>
        )}

        {hero && (
          <Pressable style={styles.hero} onPress={() => setSelected(hero)}>
            {hero.backdrop ? <Image source={{uri: hero.backdrop}} style={StyleSheet.absoluteFillObject} resizeMode="cover" /> : null}
            <View style={styles.heroShade} />
            <View style={styles.heroBody}>
              <Text style={styles.original}>ODIUMFLIX</Text>
              <Text style={styles.heroTitle}>{hero.title}</Text>
              <Text style={styles.heroMeta}>
                {[hero.year, hero.duration, hero.qualities[0]].filter(Boolean).join(' · ')}
              </Text>
              <Text style={styles.heroDescription} numberOfLines={3}>{hero.description}</Text>
              <View style={styles.heroActions}>
                <Pressable style={styles.playButton} onPress={() => setSelected(hero)}>
                  <Text style={styles.playText}>▶ Bilgiler</Text>
                </Pressable>
                {hero.trailer ? (
                  <Pressable style={styles.trailerButton} onPress={() => Linking.openURL(hero.trailer!)}>
                    <Text style={styles.trailerText}>Fragman</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          </Pressable>
        )}

        {sections.map(section => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rail}>
              {section.data.map(item => (
                <Pressable key={item.id} style={styles.card} onPress={() => setSelected(item)}>
                  {item.poster || item.backdrop ? (
                    <Image source={{uri: item.poster || item.backdrop}} style={StyleSheet.absoluteFillObject} resizeMode="cover" />
                  ) : null}
                  <View style={styles.cardShade} />
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  <Text style={styles.cardMeta}>{item.duration}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        ))}
      </ScrollView>

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.sheet}>
            <Pressable style={styles.close} onPress={() => setSelected(null)}><Text style={styles.closeText}>×</Text></Pressable>
            {selected?.backdrop ? <Image source={{uri: selected.backdrop}} style={styles.sheetImage} resizeMode="cover" /> : <View style={styles.sheetImage} />}
            <View style={styles.sheetBody}>
              <Text style={styles.sheetTitle}>{selected?.title}</Text>
              <Text style={styles.sheetMeta}>
                {[selected?.year, selected?.duration, ...(selected?.genres || [])].filter(Boolean).join(' · ')}
              </Text>
              <Text style={styles.description}>{selected?.description}</Text>
              <Text style={styles.label}>Kaliteler</Text>
              <Text style={styles.value}>{selected?.qualities.join(', ') || 'Belirtilmedi'}</Text>
              <Text style={styles.label}>Sesler</Text>
              <Text style={styles.value}>{selected?.audio.join(', ') || 'Sessiz içerik'}</Text>
              <Text style={styles.label}>Altyazılar</Text>
              <Text style={styles.value}>{selected?.subtitles.join(', ') || 'Altyazı yok'}</Text>
              {selected?.trailer ? (
                <Pressable style={styles.playButton} onPress={() => Linking.openURL(selected.trailer!)}>
                  <Text style={styles.playText}>Fragmanı aç</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

export default function App() {
  return <ErrorBoundary><OdiumFlixApp /></ErrorBoundary>;
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: '#070709'},
  scroll: {paddingBottom: 48},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 28},
  header: {height: 64, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: 10},
  brandMark: {width: 30, height: 30, borderRadius: 9, backgroundColor: '#ff365f', alignItems: 'center', justifyContent: 'center'},
  brandMarkText: {color: '#fff', fontWeight: '900', fontSize: 18},
  logo: {color: '#fff', fontWeight: '900', letterSpacing: 2},
  muted: {color: '#8f8f9b', textAlign: 'center', lineHeight: 20},
  notice: {margin: 16, padding: 18, borderRadius: 16, backgroundColor: '#211017', borderWidth: 1, borderColor: '#ff365f44'},
  noticeTitle: {color: '#fff', fontWeight: '800', fontSize: 17, marginBottom: 8},
  secondaryButton: {alignSelf: 'center', marginTop: 14, borderWidth: 1, borderColor: '#ffffff22', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10},
  secondaryButtonText: {color: '#fff', fontWeight: '700'},
  empty: {margin: 16, minHeight: 420, alignItems: 'center', justifyContent: 'center', padding: 30, borderRadius: 24, backgroundColor: '#111116', borderWidth: 1, borderColor: '#ffffff10'},
  emptyIcon: {color: '#ff365f', fontSize: 52, fontWeight: '200'},
  emptyTitle: {color: '#fff', fontSize: 24, fontWeight: '800', marginVertical: 10},
  hero: {height: 520, marginHorizontal: 14, borderRadius: 22, overflow: 'hidden', backgroundColor: '#17171e', justifyContent: 'flex-end'},
  heroShade: {position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(0,0,0,.38)'},
  heroBody: {padding: 24},
  original: {color: '#ff8aa2', fontWeight: '800', letterSpacing: 3, fontSize: 10},
  heroTitle: {color: '#fff', fontSize: 46, fontWeight: '900', marginVertical: 8},
  heroMeta: {color: '#e0e0e8', fontSize: 12},
  heroDescription: {color: '#e2e2e8', lineHeight: 20, marginTop: 12},
  heroActions: {flexDirection: 'row', gap: 10, marginTop: 18},
  playButton: {backgroundColor: '#fff', paddingHorizontal: 20, height: 44, borderRadius: 11, alignItems: 'center', justifyContent: 'center'},
  playText: {color: '#09090c', fontWeight: '900'},
  trailerButton: {backgroundColor: '#ffffff22', paddingHorizontal: 20, height: 44, borderRadius: 11, alignItems: 'center', justifyContent: 'center'},
  trailerText: {color: '#fff', fontWeight: '800'},
  section: {marginTop: 26},
  sectionTitle: {color: '#fff', fontSize: 19, fontWeight: '900', paddingHorizontal: 16, marginBottom: 11},
  rail: {paddingHorizontal: 16, gap: 10},
  card: {width: 245, height: 145, borderRadius: 14, overflow: 'hidden', backgroundColor: '#18181f', justifyContent: 'flex-end', padding: 13},
  cardShade: {position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(0,0,0,.35)'},
  cardTitle: {color: '#fff', fontWeight: '900', fontSize: 17},
  cardMeta: {color: '#c8c8d0', fontSize: 11, marginTop: 3},
  modalBackdrop: {flex: 1, backgroundColor: 'rgba(0,0,0,.72)', justifyContent: 'flex-end'},
  sheet: {maxHeight: '90%', backgroundColor: '#15151b', borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: 'hidden'},
  close: {position: 'absolute', zIndex: 4, right: 14, top: 14, width: 38, height: 38, borderRadius: 19, backgroundColor: '#000b', alignItems: 'center', justifyContent: 'center'},
  closeText: {color: '#fff', fontSize: 25},
  sheetImage: {height: 280, width: '100%', backgroundColor: '#1c1c24'},
  sheetBody: {padding: 20},
  sheetTitle: {color: '#fff', fontSize: 34, fontWeight: '900'},
  sheetMeta: {color: '#9f9faa', marginTop: 6},
  description: {color: '#e3e3e9', lineHeight: 22, marginVertical: 16},
  label: {color: '#ff7892', fontSize: 11, fontWeight: '800', marginTop: 10, textTransform: 'uppercase'},
  value: {color: '#d2d2da', marginTop: 4, lineHeight: 19},
  errorTitle: {color: '#fff', fontSize: 24, fontWeight: '900'},
});
