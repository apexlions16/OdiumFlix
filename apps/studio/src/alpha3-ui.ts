const applyAlpha3Copy=()=>{
  document.querySelectorAll('small').forEach(node=>{if(node.textContent?.includes('STUDIO 0.3 α2'))node.textContent='STUDIO 0.3 α3';});
  document.querySelectorAll('option[value="auto"]').forEach(node=>{node.textContent='Oynatılabilir HLS · önerilen';});
  document.querySelectorAll('option[value="split"]').forEach(node=>{node.textContent='Oynatılabilir HLS · video/ses/altyazı';});
  document.querySelectorAll('option[value="direct"]').forEach(node=>{node.textContent='Yalnız kaynak dosya · MKV oynatılmayabilir';});
  document.querySelectorAll('h1').forEach(node=>{if(node.textContent==='Kaliteyi değiştirmeden yükle')node.textContent='MKV’den oynatılabilir akış oluştur';});
  document.querySelectorAll('.media-header span').forEach(node=>{if(node.textContent?.includes('Seçtiğin kalite yalnız etikettir'))node.textContent='Video kalitesi korunur; HF’ye playback.m3u8, video.m3u8 ve gerçek HLS medya parçaları yüklenir.';});
  document.querySelectorAll('.quality-block p').forEach(node=>{node.textContent='Önerilen mod playback.m3u8 üretir. Kaynak çözünürlük değişmez; video stream-copy ile paketlenir.';});
  document.querySelectorAll('.media-footer span').forEach(node=>{node.textContent='MKV kaynak kapsayıcıdır; doğrudan tarayıcı oynatma formatı değildir. Önerilen HLS modu kaliteyi düşürmeden oynatma paketi üretir.';});
};
new MutationObserver(applyAlpha3Copy).observe(document.documentElement,{childList:true,subtree:true});
applyAlpha3Copy();
