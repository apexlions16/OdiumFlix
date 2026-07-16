from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from media_common import (
    BatchItem, PipelineError, ProbeResult, Track, enforce_folder_limits, ffprobe,
    opaque_asset_id, parse_imdb_id, quality_from_height, quality_rank, safe_slug, track_dicts,
)
from media_metadata import fetch_metadata
from media_packaging import add_subtitle, copy_direct, extract_audio_track, package_video_lossless


def variant_sources(item: BatchItem, source: Path, source_probe: ProbeResult) -> list[tuple[str, Path, ProbeResult]]:
    prepared = dict(item.prepared_variants or {})
    source_height = next((track.height for track in source_probe.tracks if track.kind == "video"), None)
    source_label = item.source_quality or quality_from_height(source_height)
    prepared.setdefault(source_label, str(source))
    values: list[tuple[str, Path, ProbeResult]] = []
    seen: set[Path] = set()
    for label, value in prepared.items():
        variant = Path(value).expanduser().resolve()
        if variant in seen:
            continue
        if not variant.exists():
            raise PipelineError(f"Hazır kalite dosyası bulunamadı ({label}): {variant}")
        seen.add(variant)
        values.append((label or quality_from_height(None), variant, source_probe if variant == source else ffprobe(variant)))
    values.sort(key=lambda value: quality_rank(value[0]), reverse=True)
    return values


def write_master_manifest(asset_dir: Path, manifest: dict[str, Any]) -> str | None:
    qualities = [q for q in manifest["playback"]["qualities"] if q.get("playlist")]
    if not qualities:
        return None
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    audio = [track for track in manifest["playback"]["audio"] if track.get("playlist")]
    subtitles = [track for track in manifest["playback"]["subtitles"] if track.get("playlist")]
    for track in audio:
        lines.append(
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME=' + json.dumps(track["name"]) +
            ',LANGUAGE=' + json.dumps(track["language"]) + ',AUTOSELECT=YES,DEFAULT=' +
            ("YES" if track["default"] else "NO") + ',URI=' + json.dumps(track["playlist"])
        )
    for track in subtitles:
        lines.append(
            '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME=' + json.dumps(track["name"]) +
            ',LANGUAGE=' + json.dumps(track["language"]) + ',AUTOSELECT=YES,DEFAULT=' +
            ("YES" if track["default"] else "NO") + ',FORCED=' + ("YES" if track["forced"] else "NO") +
            ',URI=' + json.dumps(track["playlist"])
        )
    for quality in sorted(qualities, key=lambda value: quality_rank(value["name"])):
        width = quality.get("actualWidth") or 1920
        height = quality.get("actualHeight") or 1080
        bandwidth = quality.get("bitRate") or max(1_000_000, int(width * height * 4.2))
        attrs = [f"BANDWIDTH={bandwidth}", f"RESOLUTION={width}x{height}"]
        if audio: attrs.append('AUDIO="audio"')
        if subtitles: attrs.append('SUBTITLES="subs"')
        lines.extend(["#EXT-X-STREAM-INF:" + ",".join(attrs), quality["playlist"]])
    master = asset_dir / "master.m3u8"
    master.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return master.name


def process_item(
    item: BatchItem, output_root: Path, *, overwrite: bool = False,
    tmdb_token: str | None = None, metadata_language: str = "tr-TR",
) -> dict[str, Any]:
    source = Path(item.source).expanduser().resolve()
    if not source.exists():
        raise PipelineError(f"Kaynak bulunamadı: {source}")
    source_probe = ffprobe(source)
    variants = variant_sources(item, source, source_probe)
    if not any(track.kind == "video" for _, _, probe in variants for track in probe.tracks):
        raise PipelineError(f"Video parçası bulunamadı: {source}")

    asset_id = item.asset_id or opaque_asset_id()
    asset_dir = output_root / "objects" / asset_id[:2] / asset_id
    if asset_dir.exists() and overwrite:
        shutil.rmtree(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)

    imdb_id = parse_imdb_id(item.imdb_id or item.imdb_url)
    warnings: list[str] = []
    metadata: dict[str, Any] | None = None
    if imdb_id:
        if tmdb_token:
            try:
                metadata = fetch_metadata(title=None, imdb_id=imdb_id, token=tmdb_token, language=metadata_language)
            except PipelineError as exc:
                warnings.append(str(exc))
        else:
            warnings.append("TMDB anahtarı girilmedi; IMDb metadata adımı atlandı.")
    if item.target_qualities and set(item.target_qualities) != {label for label, _, _ in variants}:
        warnings.append("Eski 'üretilecek kaliteler' ayarı yok sayıldı; yalnız yüklediğin kalite dosyaları korundu.")
    if item.video_codec not in {"auto", "copy", ""}:
        warnings.append(f"Video kodeği '{item.video_codec}' isteği yok sayıldı; görüntü kalite kaybı olmadan stream-copy yapıldı.")

    primary_label, primary_source, primary_probe = variants[0]
    primary_audio = [track for track in primary_probe.tracks if track.kind == "audio"]
    primary_subtitles = [track for track in primary_probe.tracks if track.kind == "subtitle"]
    mode = item.processing_mode if item.processing_mode in {"auto", "split", "direct"} else "auto"
    direct_mode = mode == "direct" or (mode == "auto" and item.direct_silent_mkv and not primary_audio and not primary_subtitles and len(variants) == 1)

    manifest: dict[str, Any] = {
        "schemaVersion": 3, "assetId": asset_id,
        "title": metadata.get("title") if metadata and metadata.get("title") else item.title,
        "userTitle": item.title, "contentType": item.content_type,
        "externalIds": {"imdb": imdb_id, "tmdb": metadata.get("tmdbId") if metadata else item.tmdb_id},
        "episode": {"season": item.season, "number": item.episode} if item.season is not None else None,
        "durationSeconds": primary_probe.duration_seconds,
        "source": {
            "originalName": source.name, "container": source_probe.format_name,
            "declaredQuality": item.source_quality or primary_label, "sizeBytes": source_probe.size_bytes,
            "archived": bool(item.keep_original), "videoPolicy": "lossless-stream-copy-only",
        },
        "metadata": metadata,
        "trailerUrl": item.trailer_url or (metadata or {}).get("trailerUrl"),
        "playback": {"master": None, "qualities": [], "audio": [], "subtitles": [], "direct": direct_mode},
        "tracks": track_dicts(primary_probe), "warnings": warnings, "createdAt": int(time.time()),
    }

    for label, variant, probe in variants:
        folder = asset_dir / "video" / safe_slug(label)
        quality = copy_direct(variant, folder, label, probe) if direct_mode else package_video_lossless(variant, folder, label, probe)
        manifest["playback"]["qualities"].append(quality)

    if not direct_mode:
        audio_sources: list[tuple[Path, Track]] = [(primary_source, track) for track in primary_audio]
        for external_path in item.external_audio:
            external = Path(external_path).expanduser().resolve()
            external_probe = ffprobe(external)
            external_track = next((track for track in external_probe.tracks if track.kind == "audio"), None)
            if external_track:
                audio_sources.append((external, external_track))
            else:
                warnings.append(f"Harici ses parçası bulunamadı: {external.name}")
        for order, (audio_source, track) in enumerate(audio_sources):
            folder = asset_dir / "audio" / f"a{order:02d}-{safe_slug(track.language)}"
            manifest["playback"]["audio"].append(extract_audio_track(audio_source, track, folder, item.audio_codec or "copy", order))

        subtitle_sources: list[tuple[Path, Track, bool]] = [(primary_source, track, False) for track in primary_subtitles]
        for external_path in item.external_subtitles:
            external = Path(external_path).expanduser().resolve()
            try:
                external_probe = ffprobe(external)
                track = next((value for value in external_probe.tracks if value.kind == "subtitle"), None)
            except PipelineError:
                track = None
            if track is None:
                track = Track(index=0, kind="subtitle", codec=external.suffix.lstrip(".") or "text", language="und", title=external.stem)
            subtitle_sources.append((external, track, True))
        for order, (subtitle_source, track, external) in enumerate(subtitle_sources):
            folder = asset_dir / "subtitles" / f"s{order:02d}-{safe_slug(track.language)}"
            manifest["playback"]["subtitles"].append(add_subtitle(
                subtitle_source, track, folder, primary_probe.duration_seconds, order,
                external=external, keep_original=item.keep_subtitle_originals,
            ))

    if item.keep_original:
        archive = asset_dir / "source"
        archive.mkdir(parents=True, exist_ok=True)
        archived = archive / f"original{source.suffix.lower() or '.mkv'}"
        shutil.copy2(source, archived)
        manifest["source"]["archiveFile"] = archived.relative_to(asset_dir).as_posix()

    manifest["playback"]["master"] = write_master_manifest(asset_dir, manifest)
    (asset_dir / "asset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    enforce_folder_limits(asset_dir)
    return manifest
