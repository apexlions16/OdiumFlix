#!/usr/bin/env python3
"""OdiumFlix local-first media splitter, metadata loader and transactional uploader."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

FOLDER_FILE_LIMIT = 9000
DEFAULT_MAX_OPS_PER_COMMIT = 100
CATALOG_SCHEMA_VERSION = 2

QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    "2160p": {"width": 3840, "height": 2160, "bandwidth": 20_000_000, "maxrate": "20M", "bufsize": "40M", "crf": 18},
    "1440p": {"width": 2560, "height": 1440, "bandwidth": 11_000_000, "maxrate": "11M", "bufsize": "22M", "crf": 19},
    "1080p+": {"width": 1920, "height": 1080, "bandwidth": 8_500_000, "maxrate": "8500k", "bufsize": "17M", "crf": 18},
    "1080p": {"width": 1920, "height": 1080, "bandwidth": 5_500_000, "maxrate": "5500k", "bufsize": "11M", "crf": 20},
    "720p": {"width": 1280, "height": 720, "bandwidth": 3_000_000, "maxrate": "3000k", "bufsize": "6000k", "crf": 21},
    "480p": {"width": 854, "height": 480, "bandwidth": 1_400_000, "maxrate": "1400k", "bufsize": "2800k", "crf": 22},
}

VIDEO_ENCODERS = {
    "h264": "libx264",
    "h265": "libx265",
    "av1": "libaom-av1",
    "vp9": "libvpx-vp9",
}

AUDIO_ENCODERS: dict[str, dict[str, str]] = {
    "aac": {"encoder": "aac", "extension": ".m4a"},
    "mp3": {"encoder": "libmp3lame", "extension": ".mp3"},
    "ac3": {"encoder": "ac3", "extension": ".ac3"},
    "eac3": {"encoder": "eac3", "extension": ".eac3"},
    "opus": {"encoder": "libopus", "extension": ".opus"},
    "vorbis": {"encoder": "libvorbis", "extension": ".ogg"},
    "flac": {"encoder": "flac", "extension": ".flac"},
    "alac": {"encoder": "alac", "extension": ".m4a"},
    "pcm_s16le": {"encoder": "pcm_s16le", "extension": ".wav"},
    "pcm_s24le": {"encoder": "pcm_s24le", "extension": ".wav"},
}

COPY_AUDIO_EXTENSIONS = {
    "aac": ".m4a", "mp3": ".mp3", "ac3": ".ac3", "eac3": ".eac3",
    "opus": ".opus", "vorbis": ".ogg", "flac": ".flac", "alac": ".m4a",
    "truehd": ".thd", "dts": ".dts", "pcm_s16le": ".wav", "pcm_s24le": ".wav",
}


class PipelineError(RuntimeError):
    pass


@dataclass(slots=True)
class Track:
    index: int
    kind: str
    codec: str
    language: str
    title: str
    channels: int | None = None
    channel_layout: str | None = None
    width: int | None = None
    height: int | None = None
    default: bool = False
    forced: bool = False


@dataclass(slots=True)
class ProbeResult:
    path: str
    duration_seconds: float
    format_name: str
    size_bytes: int
    tracks: list[Track]


@dataclass(slots=True)
class BatchItem:
    source: str
    title: str
    content_type: str = "movie"
    source_quality: str | None = None
    target_qualities: list[str] | None = None
    asset_id: str | None = None
    imdb_id: str | None = None
    imdb_url: str | None = None
    tmdb_id: int | None = None
    season: int | None = None
    episode: int | None = None
    prepared_variants: dict[str, str] | None = None
    processing_mode: str = "auto"
    direct_silent_mkv: bool = True
    keep_original: bool = False
    video_codec: str = "auto"
    audio_codec: str = "aac"
    external_audio: list[str] = field(default_factory=list)
    external_subtitles: list[str] = field(default_factory=list)
    keep_subtitle_originals: bool = True
    trailer_url: str | None = None


def run(command: Sequence[str], *, capture: bool = False) -> str:
    resolved = list(command)
    if resolved and resolved[0] == "ffmpeg":
        resolved[0] = os.getenv("ODIUM_FFMPEG", "ffmpeg")
    elif resolved and resolved[0] == "ffprobe":
        resolved[0] = os.getenv("ODIUM_FFPROBE", "ffprobe")
    try:
        result = subprocess.run(
            resolved,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as exc:
        raise PipelineError(f"Required executable not found: {resolved[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PipelineError(f"Command failed ({exc.returncode}): {' '.join(command)}\n{detail}") from exc
    return result.stdout if capture else ""


def run_soft(command: Sequence[str]) -> tuple[bool, str]:
    resolved = list(command)
    if resolved and resolved[0] == "ffmpeg":
        resolved[0] = os.getenv("ODIUM_FFMPEG", "ffmpeg")
    elif resolved and resolved[0] == "ffprobe":
        resolved[0] = os.getenv("ODIUM_FFPROBE", "ffprobe")
    result = subprocess.run(resolved, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0, (result.stderr or result.stdout or "").strip()


def normalize_language(value: Any) -> str:
    language = str(value or "und").lower().strip()
    aliases = {
        "tur": "tr", "eng": "en", "deu": "de", "ger": "de", "fra": "fr",
        "fre": "fr", "spa": "es", "ita": "it", "jpn": "ja", "kor": "ko",
        "por": "pt", "rus": "ru", "ara": "ar",
    }
    return aliases.get(language, language)


def default_track_title(kind: str, language: str, stream: dict[str, Any]) -> str:
    if kind == "video":
        return f"Video {stream.get('height') or ''}p".strip()
    if kind == "audio":
        channels = stream.get("channels")
        return f"{language.upper()} Audio" + (f" {channels}ch" if channels else "")
    return f"{language.upper()} Subtitle"


def ffprobe(path: Path) -> ProbeResult:
    raw = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture=True)
    data = json.loads(raw)
    tracks: list[Track] = []
    for stream in data.get("streams", []):
        kind = stream.get("codec_type", "unknown")
        if kind not in {"video", "audio", "subtitle"}:
            continue
        tags = stream.get("tags") or {}
        disposition = stream.get("disposition") or {}
        language = normalize_language(tags.get("language"))
        tracks.append(
            Track(
                index=int(stream["index"]),
                kind=kind,
                codec=str(stream.get("codec_name") or "unknown"),
                language=language,
                title=str(tags.get("title") or default_track_title(kind, language, stream)).strip(),
                channels=int(stream["channels"]) if stream.get("channels") else None,
                channel_layout=stream.get("channel_layout"),
                width=int(stream["width"]) if stream.get("width") else None,
                height=int(stream["height"]) if stream.get("height") else None,
                default=bool(disposition.get("default")),
                forced=bool(disposition.get("forced")),
            )
        )
    fmt = data.get("format") or {}
    return ProbeResult(
        path=str(path.resolve()),
        duration_seconds=float(fmt.get("duration") or 0),
        format_name=str(fmt.get("format_name") or path.suffix.lstrip(".")),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
        tracks=tracks,
    )


def safe_slug(value: str) -> str:
    value = value.strip().lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "untitled"


def opaque_asset_id() -> str:
    return uuid.uuid4().hex


def parse_imdb_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b(tt\d{5,12})\b", value, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def quality_from_height(height: int | None) -> str | None:
    if not height:
        return None
    if height >= 2160:
        return "2160p"
    if height >= 1440:
        return "1440p"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    return "480p"


def choose_targets(source_quality: str | None, requested: Sequence[str] | None) -> list[str]:
    if requested:
        invalid = [q for q in requested if q not in QUALITY_PROFILES]
        if invalid:
            raise PipelineError(f"Unsupported qualities: {', '.join(invalid)}")
        return list(dict.fromkeys(requested))
    source_height = QUALITY_PROFILES.get(source_quality or "", {}).get("height", 1080)
    return [q for q, profile in QUALITY_PROFILES.items() if profile["height"] <= source_height and q != "1440p"]


def write_single_file_playlist(path: Path, filename: str, duration: float) -> None:
    path.write_text(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        f"#EXT-X-TARGETDURATION:{max(1, int(duration + .999))}\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:{duration:.3f},\n"
        f"{filename}\n"
        "#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )


def video_codec_args(codec: str, profile: dict[str, Any], *, can_copy: bool) -> list[str]:
    if codec == "copy":
        if not can_copy:
            raise PipelineError("video_codec=copy yalnızca hazırlanmış kalite dosyalarında kullanılabilir")
        return ["-c:v", "copy"]
    encoder = VIDEO_ENCODERS.get(codec)
    if not encoder:
        raise PipelineError(f"Unsupported video codec: {codec}")
    args = ["-c:v", encoder]
    if codec in {"h264", "h265"}:
        args += ["-preset", "medium", "-crf", str(profile["crf"]), "-maxrate", str(profile["maxrate"]), "-bufsize", str(profile["bufsize"])]
    elif codec == "av1":
        args += ["-crf", str(profile["crf"] + 10), "-b:v", "0", "-cpu-used", "5"]
    elif codec == "vp9":
        args += ["-crf", str(profile["crf"] + 9), "-b:v", "0", "-deadline", "good"]
    return args


def process_video_variant(
    variant_source: Path,
    folder: Path,
    quality: str,
    profile: dict[str, Any],
    video_codec: str,
    *,
    prepared_exact: bool,
) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    playlist, segment = folder / "index.m3u8", folder / "stream.m4s"
    resolved_codec = "copy" if video_codec == "auto" and prepared_exact else ("h264" if video_codec == "auto" else video_codec)
    command = ["ffmpeg", "-y", "-i", str(variant_source), "-map", "0:v:0", "-an", "-sn"]
    if not (resolved_codec == "copy" and prepared_exact):
        scale = f"scale=-2:{profile['height']}:force_original_aspect_ratio=decrease:force_divisible_by=2"
        command += ["-vf", scale]
    command += video_codec_args(resolved_codec, profile, can_copy=prepared_exact)
    if resolved_codec == "h264":
        command += ["-pix_fmt", "yuv420p", "-g", "144", "-keyint_min", "144", "-sc_threshold", "0"]
    elif resolved_codec == "h265":
        command += ["-tag:v", "hvc1", "-pix_fmt", "yuv420p10le", "-g", "144", "-keyint_min", "144"]
    command += [
        "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
        "-hls_segment_type", "fmp4", "-hls_flags", "single_file+independent_segments",
        "-hls_fmp4_init_filename", f"init-{safe_slug(quality)}.mp4",
        "-hls_segment_filename", str(segment), str(playlist),
    ]
    run(command)
    return {
        "name": quality,
        "width": profile["width"],
        "height": profile["height"],
        "bandwidth": profile["bandwidth"],
        "codec": resolved_codec,
        "playlist": playlist.relative_to(folder.parent.parent).as_posix(),
    }


def audio_output_spec(requested: str, source_codec: str) -> tuple[str, str, list[str]]:
    if requested == "copy":
        extension = COPY_AUDIO_EXTENSIONS.get(source_codec, ".mka")
        return source_codec, extension, ["-c:a", "copy"]
    spec = AUDIO_ENCODERS.get(requested)
    if not spec:
        raise PipelineError(f"Unsupported audio codec: {requested}. 'copy' kaynak kodeğini aynen korur.")
    args = ["-c:a", spec["encoder"]]
    if requested in {"aac", "mp3", "ac3", "eac3", "opus", "vorbis"}:
        args += ["-b:a", "384k"]
    return requested, spec["extension"], args


def process_audio_track(
    input_path: Path,
    track: Track,
    folder: Path,
    requested_codec: str,
    *,
    map_expression: str,
    duration: float,
    name_override: str | None = None,
) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    codec_name, extension, codec_args = audio_output_spec(requested_codec, track.codec)
    output = folder / f"track{extension}"
    run(["ffmpeg", "-y", "-i", str(input_path), "-map", map_expression, "-vn", "-sn", *codec_args, str(output)])
    playlist = folder / "index.m3u8"
    write_single_file_playlist(playlist, output.name, duration)
    return {
        "id": folder.name,
        "language": track.language,
        "name": name_override or track.title,
        "sourceCodec": track.codec,
        "codec": codec_name,
        "channels": track.channels,
        "default": track.default,
        "playlist": playlist.relative_to(folder.parent.parent).as_posix(),
        "file": output.relative_to(folder.parent.parent).as_posix(),
    }


def export_subtitle(
    input_path: Path,
    track: Track,
    folder: Path,
    *,
    map_expression: str,
    duration: float,
    keep_original: bool,
    external_original: Path | None = None,
) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "id": folder.name,
        "language": track.language,
        "name": track.title,
        "sourceCodec": track.codec,
        "forced": track.forced,
        "default": track.default,
        "format": "raw",
    }
    vtt = folder / "captions.vtt"
    ok, error = run_soft(["ffmpeg", "-y", "-i", str(input_path), "-map", map_expression, "-f", "webvtt", str(vtt)])
    if ok and vtt.exists() and vtt.stat().st_size:
        playlist = folder / "index.m3u8"
        write_single_file_playlist(playlist, vtt.name, duration)
        result.update({
            "format": "vtt",
            "playlist": playlist.relative_to(folder.parent.parent).as_posix(),
            "file": vtt.relative_to(folder.parent.parent).as_posix(),
        })
    else:
        result["conversionError"] = error[-500:] if error else "WebVTT conversion unsupported"
    if keep_original:
        raw_dir = folder / "raw"
        raw_dir.mkdir(exist_ok=True)
        if external_original:
            raw = raw_dir / external_original.name
            shutil.copy2(external_original, raw)
        else:
            raw = raw_dir / f"track-{safe_slug(track.codec)}.mks"
            copied, copy_error = run_soft([
                "ffmpeg", "-y", "-i", str(input_path), "-map", map_expression,
                "-c", "copy", "-f", "matroska", str(raw),
            ])
            if not copied:
                result["rawExportError"] = copy_error[-500:]
        if raw.exists():
            result["originalFile"] = raw.relative_to(folder.parent.parent).as_posix()
    return result


def extract_language_from_filename(path: Path) -> str:
    bits = re.split(r"[._\-\s]+", path.stem.lower())
    for bit in reversed(bits):
        if re.fullmatch(r"[a-z]{2,3}", bit):
            return normalize_language(bit)
    return "und"


def fetch_external_audio_tracks(paths: Iterable[str]) -> list[tuple[Path, Track, float]]:
    result: list[tuple[Path, Track, float]] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise PipelineError(f"External audio does not exist: {path}")
        probe = ffprobe(path)
        audio = next((track for track in probe.tracks if track.kind == "audio"), None)
        if not audio:
            raise PipelineError(f"No audio track found: {path}")
        audio.title = path.stem
        if audio.language == "und":
            audio.language = extract_language_from_filename(path)
        result.append((path, audio, probe.duration_seconds))
    return result


def fetch_external_subtitle_tracks(paths: Iterable[str]) -> list[tuple[Path, Track, float]]:
    result: list[tuple[Path, Track, float]] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise PipelineError(f"External subtitle does not exist: {path}")
        try:
            probe = ffprobe(path)
            subtitle = next((track for track in probe.tracks if track.kind == "subtitle"), None)
            duration = probe.duration_seconds
        except PipelineError:
            subtitle = None
            duration = 0
        if not subtitle:
            subtitle = Track(
                index=0,
                kind="subtitle",
                codec=path.suffix.lstrip(".").lower() or "text",
                language=extract_language_from_filename(path),
                title=path.stem,
            )
        result.append((path, subtitle, duration))
    return result


def tmdb_request(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    url = f"https://api.themoviedb.org/3/{path.lstrip('/')}" + (f"?{query}" if query else "")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise PipelineError(f"TMDB request failed: {exc.code} {detail}") from exc


def fetch_metadata(*, title: str | None, imdb_id: str | None, token: str, language: str = "tr-TR") -> dict[str, Any]:
    if imdb_id:
        found = tmdb_request(f"find/{imdb_id}", token, {"external_source": "imdb_id", "language": language})
        candidate = (found.get("movie_results") or found.get("tv_results") or [None])[0]
        if not candidate:
            raise PipelineError(f"No TMDB record found for IMDb id {imdb_id}")
        media_type = "movie" if found.get("movie_results") else "tv"
        media_id = candidate["id"]
    elif title:
        found = tmdb_request("search/multi", token, {"query": title, "language": language, "include_adult": "false"})
        candidates = [row for row in found.get("results", []) if row.get("media_type") in {"movie", "tv"}]
        if not candidates:
            raise PipelineError(f"No metadata found for {title}")
        candidate = candidates[0]
        media_type, media_id = candidate["media_type"], candidate["id"]
    else:
        raise PipelineError("title or imdb_id is required")
    details = tmdb_request(
        f"{media_type}/{media_id}",
        token,
        {"language": language, "append_to_response": "images,external_ids,credits,videos,content_ratings,release_dates"},
    )
    cast = [
        {"name": person.get("name"), "character": person.get("character"), "profilePath": person.get("profile_path")}
        for person in (details.get("credits") or {}).get("cast", [])
    ]
    crew = [
        {"name": person.get("name"), "job": person.get("job"), "department": person.get("department")}
        for person in (details.get("credits") or {}).get("crew", [])
    ]
    videos = (details.get("videos") or {}).get("results", [])
    trailer = next(
        (f"https://www.youtube.com/watch?v={video['key']}" for video in videos if video.get("site") == "YouTube" and video.get("type") == "Trailer" and video.get("official")),
        None,
    ) or next((f"https://www.youtube.com/watch?v={video['key']}" for video in videos if video.get("site") == "YouTube"), None)
    return {
        "provider": "tmdb",
        "tmdbId": media_id,
        "imdbId": (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id") or imdb_id,
        "type": media_type,
        "title": details.get("title") or details.get("name"),
        "originalTitle": details.get("original_title") or details.get("original_name"),
        "overview": details.get("overview"),
        "releaseDate": details.get("release_date") or details.get("first_air_date"),
        "runtime": details.get("runtime") or (details.get("episode_run_time") or [None])[0],
        "genres": [genre["name"] for genre in details.get("genres", [])],
        "tagline": details.get("tagline"),
        "status": details.get("status"),
        "posterPath": details.get("poster_path"),
        "backdropPath": details.get("backdrop_path"),
        "cast": cast,
        "crew": crew,
        "trailerUrl": trailer,
    }


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "OdiumFlix/0.3"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def download_metadata_artwork(asset_dir: Path, metadata: dict[str, Any]) -> dict[str, str]:
    artwork: dict[str, str] = {}
    for key, remote_key, filename in (
        ("poster", "posterPath", "poster.jpg"),
        ("backdrop", "backdropPath", "backdrop.jpg"),
    ):
        remote = metadata.get(remote_key)
        if not remote:
            continue
        destination = asset_dir / "artwork" / filename
        download_file(f"https://image.tmdb.org/t/p/original{remote}", destination)
        artwork[key] = destination.relative_to(asset_dir).as_posix()
    return artwork


def should_direct_upload(item: BatchItem, source: Path, audios: list[Track], subtitles: list[Track]) -> bool:
    if item.processing_mode == "direct":
        return True
    if item.processing_mode == "split":
        return False
    return item.direct_silent_mkv and source.suffix.lower() == ".mkv" and not audios and not subtitles


def process_item(
    item: BatchItem,
    output_root: Path,
    *,
    overwrite: bool = False,
    tmdb_token: str | None = None,
    metadata_language: str = "tr-TR",
) -> dict[str, Any]:
    source = Path(item.source).expanduser().resolve()
    if not source.exists():
        raise PipelineError(f"Source does not exist: {source}")
    if item.processing_mode not in {"auto", "split", "direct"}:
        raise PipelineError(f"Unsupported processing mode: {item.processing_mode}")
    asset_id = item.asset_id or opaque_asset_id()
    asset_dir = output_root / "objects" / asset_id[:2] / asset_id
    if asset_dir.exists() and overwrite:
        shutil.rmtree(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)
    probe = ffprobe(source)
    videos = [track for track in probe.tracks if track.kind == "video"]
    audios = [track for track in probe.tracks if track.kind == "audio"]
    subtitles = [track for track in probe.tracks if track.kind == "subtitle"]
    if not videos and not item.prepared_variants:
        raise PipelineError(f"No video track detected: {source}")
    detected = item.source_quality or quality_from_height(videos[0].height if videos else None)
    imdb_id = parse_imdb_id(item.imdb_id or item.imdb_url)
    metadata: dict[str, Any] | None = None
    if tmdb_token and (imdb_id or item.title):
        metadata = fetch_metadata(title=item.title, imdb_id=imdb_id, token=tmdb_token, language=metadata_language)
        item.tmdb_id = int(metadata["tmdbId"])
        item.title = metadata.get("title") or item.title
    if metadata and item.trailer_url:
        metadata["trailerUrl"] = item.trailer_url
    direct = should_direct_upload(item, source, audios, subtitles)
    manifest: dict[str, Any] = {
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "assetId": asset_id,
        "title": item.title,
        "contentType": item.content_type,
        "source": {
            "originalName": source.name,
            "container": probe.format_name,
            "quality": detected,
            "sizeBytes": probe.size_bytes,
            "archived": bool(item.keep_original),
        },
        "externalIds": {"imdb": imdb_id, "tmdb": item.tmdb_id},
        "episode": {"season": item.season, "number": item.episode} if item.season is not None else None,
        "durationSeconds": probe.duration_seconds,
        "metadata": metadata,
        "artwork": {},
        "playback": {
            "mode": "direct" if direct else "hls",
            "master": None if direct else "master.m3u8",
            "directFile": None,
            "qualities": [],
            "audio": [],
            "subtitles": [],
        },
        "tracks": [asdict(track) for track in probe.tracks],
        "createdAt": int(time.time()),
    }
    if metadata:
        manifest["artwork"] = download_metadata_artwork(asset_dir, metadata)
    if direct:
        direct_dir = asset_dir / "video" / "direct"
        direct_dir.mkdir(parents=True, exist_ok=True)
        direct_file = direct_dir / f"source{source.suffix.lower() or '.mkv'}"
        shutil.copy2(source, direct_file)
        manifest["playback"]["directFile"] = direct_file.relative_to(asset_dir).as_posix()
        manifest["playback"]["qualities"] = [{
            "name": detected or "original",
            "codec": videos[0].codec if videos else "unknown",
            "file": direct_file.relative_to(asset_dir).as_posix(),
            "width": videos[0].width if videos else None,
            "height": videos[0].height if videos else None,
        }]
    else:
        targets = choose_targets(detected, item.target_qualities)
        prepared = item.prepared_variants or {}
        for quality in targets:
            profile = QUALITY_PROFILES[quality]
            variant_source = Path(prepared.get(quality, source)).expanduser().resolve()
            if not variant_source.exists():
                raise PipelineError(f"Prepared variant does not exist for {quality}: {variant_source}")
            manifest["playback"]["qualities"].append(
                process_video_variant(
                    variant_source,
                    asset_dir / "video" / safe_slug(quality),
                    quality,
                    profile,
                    item.video_codec,
                    prepared_exact=quality in prepared,
                )
            )
        for order, track in enumerate(audios):
            track_id = f"a{order:02d}-{safe_slug(track.language)}"
            result = process_audio_track(
                source,
                track,
                asset_dir / "audio" / track_id,
                item.audio_codec,
                map_expression=f"0:{track.index}",
                duration=probe.duration_seconds,
            )
            result["default"] = track.default or order == 0
            manifest["playback"]["audio"].append(result)
        for external_order, (audio_path, track, duration) in enumerate(fetch_external_audio_tracks(item.external_audio), start=len(audios)):
            track_id = f"a{external_order:02d}-{safe_slug(track.language)}"
            result = process_audio_track(
                audio_path,
                track,
                asset_dir / "audio" / track_id,
                item.audio_codec,
                map_expression="0:a:0",
                duration=duration or probe.duration_seconds,
                name_override=audio_path.stem,
            )
            result["default"] = not manifest["playback"]["audio"]
            manifest["playback"]["audio"].append(result)
        for order, track in enumerate(subtitles):
            manifest["playback"]["subtitles"].append(
                export_subtitle(
                    source,
                    track,
                    asset_dir / "subtitles" / f"s{order:02d}-{safe_slug(track.language)}",
                    map_expression=f"0:{track.index}",
                    duration=probe.duration_seconds,
                    keep_original=item.keep_subtitle_originals,
                )
            )
        start = len(subtitles)
        for external_order, (subtitle_path, track, duration) in enumerate(fetch_external_subtitle_tracks(item.external_subtitles), start=start):
            manifest["playback"]["subtitles"].append(
                export_subtitle(
                    subtitle_path,
                    track,
                    asset_dir / "subtitles" / f"s{external_order:02d}-{safe_slug(track.language)}",
                    map_expression="0:s:0",
                    duration=duration or probe.duration_seconds,
                    keep_original=item.keep_subtitle_originals,
                    external_original=subtitle_path,
                )
            )
        write_master_manifest(asset_dir, manifest)
        if item.keep_original:
            source_dir = asset_dir / "source"
            source_dir.mkdir(exist_ok=True)
            original = source_dir / f"original{source.suffix.lower() or '.mkv'}"
            shutil.copy2(source, original)
            manifest["source"]["archiveFile"] = original.relative_to(asset_dir).as_posix()
    (asset_dir / "asset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    enforce_folder_limits(asset_dir)
    return manifest


def write_master_manifest(asset_dir: Path, manifest: dict[str, Any]) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for audio in manifest["playback"]["audio"]:
        if not audio.get("playlist"):
            continue
        lines.append(
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
            f'NAME={json.dumps(audio["name"])},LANGUAGE={json.dumps(audio["language"])},'
            f'AUTOSELECT=YES,DEFAULT={"YES" if audio["default"] else "NO"},'
            f'URI={json.dumps(audio["playlist"])}'
        )
    for subtitle in manifest["playback"]["subtitles"]:
        if not subtitle.get("playlist"):
            continue
        lines.append(
            '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",'
            f'NAME={json.dumps(subtitle["name"])},LANGUAGE={json.dumps(subtitle["language"])},'
            f'AUTOSELECT=YES,DEFAULT={"YES" if subtitle["default"] else "NO"},'
            f'FORCED={"YES" if subtitle["forced"] else "NO"},URI={json.dumps(subtitle["playlist"])}'
        )
    for quality in sorted(manifest["playback"]["qualities"], key=lambda value: value.get("height") or 0):
        if not quality.get("playlist"):
            continue
        attrs = [f"BANDWIDTH={quality['bandwidth']}", f"RESOLUTION={quality['width']}x{quality['height']}"]
        if any(audio.get("playlist") for audio in manifest["playback"]["audio"]):
            attrs.append('AUDIO="audio"')
        if any(subtitle.get("playlist") for subtitle in manifest["playback"]["subtitles"]):
            attrs.append('SUBTITLES="subs"')
        lines.extend(["#EXT-X-STREAM-INF:" + ",".join(attrs), quality["playlist"]])
    (asset_dir / "master.m3u8").write_text("\n".join(lines) + "\n", encoding="utf-8")


def enforce_folder_limits(root: Path, limit: int = FOLDER_FILE_LIMIT) -> None:
    violations = [f"{folder}: {len(files)} files" for folder, _, files in os.walk(root) if len(files) > limit]
    if violations:
        raise PipelineError(f"Folder safety limit exceeded ({limit}):\n" + "\n".join(violations))


def collect_uploads(output_root: Path) -> list[tuple[Path, str]]:
    return [(path, path.relative_to(output_root).as_posix()) for path in sorted(output_root.rglob("*")) if path.is_file()]


def huggingface_base_url(repo_id: str, repo_type: str, revision: str = "main") -> str:
    prefix = {"dataset": "datasets/", "model": "", "space": "spaces/"}[repo_type]
    return f"https://huggingface.co/{prefix}{repo_id}/resolve/{revision}"


def upload_huggingface(
    output_root: Path,
    repo_id: str,
    *,
    repo_type: str = "dataset",
    token: str | None = None,
    private: bool = False,
    message: str,
    max_ops_per_commit: int = DEFAULT_MAX_OPS_PER_COMMIT,
    dry_run: bool = False,
) -> list[str]:
    uploads = collect_uploads(output_root)
    if not uploads:
        raise PipelineError("Nothing to upload")
    if dry_run:
        print(json.dumps({
            "repo": repo_id,
            "repoType": repo_type,
            "files": len(uploads),
            "commits": (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit,
        }, indent=2))
        return []
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError as exc:
        raise PipelineError("Install requirements: pip install -r tools/media_pipeline/requirements.txt") from exc
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    api = HfApi(token=token or os.getenv("HF_TOKEN"))
    create_kwargs: dict[str, Any] = {"repo_id": repo_id, "repo_type": repo_type, "private": private, "exist_ok": True}
    if repo_type == "space":
        create_kwargs["space_sdk"] = "static"
    api.create_repo(**create_kwargs)
    urls: list[str] = []
    for start in range(0, len(uploads), max_ops_per_commit):
        chunk = uploads[start:start + max_ops_per_commit]
        operations = [CommitOperationAdd(path_in_repo=remote, path_or_fileobj=str(local)) for local, remote in chunk]
        total = (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit
        suffix = "" if total == 1 else f" ({start // max_ops_per_commit + 1}/{total})"
        result = api.create_commit(
            repo_id=repo_id,
            repo_type=repo_type,
            operations=operations,
            commit_message=message + suffix,
        )
        urls.append(str(result.commit_url))
    return urls


def update_asset_files(output_root: Path, manifests: Sequence[dict[str, Any]], storage: dict[str, Any]) -> None:
    for manifest in manifests:
        manifest["storage"] = storage
        path = output_root / "objects" / manifest["assetId"][:2] / manifest["assetId"] / "asset.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def update_github_catalog(
    manifests: Sequence[dict[str, Any]],
    *,
    repository: str,
    token: str,
    branch: str = "main",
    path: str = "catalog/media/index.json",
) -> str:
    api_url = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha = None
    current: dict[str, Any] = {"schemaVersion": CATALOG_SCHEMA_VERSION, "assets": {}}
    try:
        with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers), timeout=30) as response:
            payload = json.load(response)
            sha = payload.get("sha")
            current = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise PipelineError(f"GitHub catalog read failed: {exc}") from exc
    current["schemaVersion"] = CATALOG_SCHEMA_VERSION
    assets = current.setdefault("assets", {})
    for manifest in manifests:
        assets[manifest["assetId"]] = manifest
    body: dict[str, Any] = {
        "message": f"Catalog batch: {len(manifests)} media asset(s)",
        "content": base64.b64encode(json.dumps(current, ensure_ascii=False, indent=2).encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}",
        data=json.dumps(body).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise PipelineError(f"GitHub catalog update failed: {exc.code} {exc.read().decode(errors='replace')}") from exc
    return payload["commit"]["html_url"]


def load_batch(path: Path) -> list[BatchItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise PipelineError("Batch file must contain an items array")
    return [BatchItem(**value) for value in values]


def command_analyze(args: argparse.Namespace) -> None:
    print(json.dumps(asdict(ffprobe(Path(args.source))), ensure_ascii=False, indent=2))


def command_process(args: argparse.Namespace) -> None:
    item = BatchItem(
        source=args.source,
        title=args.title,
        content_type=args.type,
        source_quality=args.source_quality,
        target_qualities=args.qualities,
        imdb_id=args.imdb_id,
        imdb_url=args.imdb_url,
        season=args.season,
        episode=args.episode,
        processing_mode=args.processing_mode,
        keep_original=args.keep_original,
        video_codec=args.video_codec,
        audio_codec=args.audio_codec,
    )
    result = process_item(
        item,
        Path(args.output),
        overwrite=args.overwrite,
        tmdb_token=args.tmdb_token or os.getenv("TMDB_API_TOKEN"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_batch(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    token = args.tmdb_token or os.getenv("TMDB_API_TOKEN")
    manifests = [
        process_item(item, output, overwrite=args.overwrite, tmdb_token=token, metadata_language=args.metadata_language)
        for item in load_batch(Path(args.config))
    ]
    storage = None
    if args.hf_repo:
        storage = {
            "provider": "huggingface",
            "repoId": args.hf_repo,
            "repoType": args.hf_repo_type,
            "revision": "main",
            "baseUrl": huggingface_base_url(args.hf_repo, args.hf_repo_type),
            "private": bool(args.hf_private),
        }
        update_asset_files(output, manifests, storage)
    (output / "batch.json").write_text(
        json.dumps({"schemaVersion": CATALOG_SCHEMA_VERSION, "assets": manifests}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    hf_urls = upload_huggingface(
        output,
        args.hf_repo,
        repo_type=args.hf_repo_type,
        private=args.hf_private,
        message=args.message,
        max_ops_per_commit=args.max_ops,
        dry_run=args.dry_run,
    ) if args.hf_repo else []
    github_url = None
    if args.github_repo and not args.dry_run:
        github_token = args.github_token or os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise PipelineError("GITHUB_TOKEN is required for catalog update")
        github_url = update_github_catalog(
            manifests,
            repository=args.github_repo,
            token=github_token,
            branch=args.github_branch,
        )
    print(json.dumps({
        "assets": len(manifests),
        "files": len(collect_uploads(output)),
        "hfCommits": hf_urls,
        "githubCommit": github_url,
        "storage": storage,
    }, ensure_ascii=False, indent=2))


def command_metadata(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("TMDB_API_TOKEN")
    if not token:
        raise PipelineError("TMDB_API_TOKEN is required")
    imdb_id = parse_imdb_id(args.imdb_id or args.imdb_url)
    print(json.dumps(fetch_metadata(title=args.title, imdb_id=imdb_id, token=token, language=args.language), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="odium-media")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("source")
    analyze.set_defaults(func=command_analyze)
    process = sub.add_parser("process")
    process.add_argument("source")
    process.add_argument("--title", required=True)
    process.add_argument("--type", default="movie")
    process.add_argument("--source-quality", choices=QUALITY_PROFILES)
    process.add_argument("--qualities", nargs="+", choices=QUALITY_PROFILES)
    process.add_argument("--imdb-id")
    process.add_argument("--imdb-url")
    process.add_argument("--season", type=int)
    process.add_argument("--episode", type=int)
    process.add_argument("--processing-mode", default="auto", choices=["auto", "split", "direct"])
    process.add_argument("--keep-original", action="store_true")
    process.add_argument("--video-codec", default="auto", choices=["auto", *VIDEO_ENCODERS, "copy"])
    process.add_argument("--audio-codec", default="aac", choices=[*AUDIO_ENCODERS, "copy"])
    process.add_argument("--tmdb-token")
    process.add_argument("--output", default="build/media")
    process.add_argument("--overwrite", action="store_true")
    process.set_defaults(func=command_process)
    batch = sub.add_parser("batch")
    batch.add_argument("config")
    batch.add_argument("--output", default="build/media")
    batch.add_argument("--hf-repo")
    batch.add_argument("--hf-repo-type", default="dataset", choices=["dataset", "model", "space"])
    batch.add_argument("--hf-private", action="store_true")
    batch.add_argument("--github-repo")
    batch.add_argument("--github-branch", default="main")
    batch.add_argument("--github-token")
    batch.add_argument("--tmdb-token")
    batch.add_argument("--metadata-language", default="tr-TR")
    batch.add_argument("--message", default="OdiumFlix batch upload")
    batch.add_argument("--max-ops", type=int, default=DEFAULT_MAX_OPS_PER_COMMIT)
    batch.add_argument("--overwrite", action="store_true")
    batch.add_argument("--dry-run", action="store_true")
    batch.set_defaults(func=command_batch)
    metadata = sub.add_parser("metadata")
    metadata.add_argument("--title")
    metadata.add_argument("--imdb-id")
    metadata.add_argument("--imdb-url")
    metadata.add_argument("--token")
    metadata.add_argument("--language", default="tr-TR")
    metadata.set_defaults(func=command_metadata)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.func(args)
        return 0
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
