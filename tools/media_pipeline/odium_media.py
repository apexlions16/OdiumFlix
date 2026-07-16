#!/usr/bin/env python3
"""OdiumFlix local media processor and transactional uploader."""
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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

FOLDER_FILE_LIMIT = 9000
DEFAULT_MAX_OPS_PER_COMMIT = 100
QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    "2160p": {"width": 3840, "height": 2160, "bandwidth": 20_000_000, "maxrate": "20M", "bufsize": "40M", "crf": 18},
    "1440p": {"width": 2560, "height": 1440, "bandwidth": 11_000_000, "maxrate": "11M", "bufsize": "22M", "crf": 19},
    "1080p+": {"width": 1920, "height": 1080, "bandwidth": 8_500_000, "maxrate": "8500k", "bufsize": "17M", "crf": 18},
    "1080p": {"width": 1920, "height": 1080, "bandwidth": 5_500_000, "maxrate": "5500k", "bufsize": "11M", "crf": 20},
    "720p": {"width": 1280, "height": 720, "bandwidth": 3_000_000, "maxrate": "3000k", "bufsize": "6000k", "crf": 21},
    "480p": {"width": 854, "height": 480, "bandwidth": 1_400_000, "maxrate": "1400k", "bufsize": "2800k", "crf": 22},
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
    tmdb_id: int | None = None
    season: int | None = None
    episode: int | None = None
    prepared_variants: dict[str, str] | None = None

def run(command: Sequence[str], *, capture: bool = False) -> str:
    resolved = list(command)
    if resolved and resolved[0] == "ffmpeg":
        resolved[0] = os.getenv("ODIUM_FFMPEG", "ffmpeg")
    elif resolved and resolved[0] == "ffprobe":
        resolved[0] = os.getenv("ODIUM_FFPROBE", "ffprobe")
    try:
        result = subprocess.run(resolved, check=True, text=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    except FileNotFoundError as exc:
        raise PipelineError(f"Required executable not found: {resolved[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PipelineError(f"Command failed ({exc.returncode}): {' '.join(command)}\n{detail}") from exc
    return result.stdout if capture else ""

def normalize_language(value: Any) -> str:
    language = str(value or "und").lower().strip()
    aliases = {"tur": "tr", "eng": "en", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr", "spa": "es", "ita": "it", "jpn": "ja"}
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
        tracks.append(Track(index=int(stream["index"]), kind=kind, codec=str(stream.get("codec_name") or "unknown"), language=language, title=str(tags.get("title") or default_track_title(kind, language, stream)).strip(), channels=int(stream["channels"]) if stream.get("channels") else None, channel_layout=stream.get("channel_layout"), width=int(stream["width"]) if stream.get("width") else None, height=int(stream["height"]) if stream.get("height") else None, default=bool(disposition.get("default")), forced=bool(disposition.get("forced"))))
    fmt = data.get("format") or {}
    return ProbeResult(path=str(path.resolve()), duration_seconds=float(fmt.get("duration") or 0), format_name=str(fmt.get("format_name") or path.suffix.lstrip(".")), size_bytes=int(fmt.get("size") or path.stat().st_size), tracks=tracks)

def safe_slug(value: str) -> str:
    value = value.strip().lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "untitled"

def opaque_asset_id() -> str:
    return uuid.uuid4().hex

def quality_from_height(height: int | None) -> str | None:
    if not height: return None
    if height >= 2160: return "2160p"
    if height >= 1440: return "1440p"
    if height >= 1080: return "1080p"
    if height >= 720: return "720p"
    return "480p"

def choose_targets(source_quality: str | None, requested: Sequence[str] | None) -> list[str]:
    if requested:
        invalid = [q for q in requested if q not in QUALITY_PROFILES]
        if invalid: raise PipelineError(f"Unsupported qualities: {', '.join(invalid)}")
        return list(dict.fromkeys(requested))
    source_height = QUALITY_PROFILES.get(source_quality or "", {}).get("height", 1080)
    return [q for q, p in QUALITY_PROFILES.items() if p["height"] <= source_height and q != "1440p"]

def process_item(item: BatchItem, output_root: Path, *, overwrite: bool = False) -> dict[str, Any]:
    source = Path(item.source).expanduser().resolve()
    if not source.exists(): raise PipelineError(f"Source does not exist: {source}")
    asset_id = item.asset_id or opaque_asset_id()
    asset_dir = output_root / "objects" / asset_id[:2] / asset_id
    if asset_dir.exists() and overwrite: shutil.rmtree(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)
    probe = ffprobe(source)
    videos = [t for t in probe.tracks if t.kind == "video"]
    audios = [t for t in probe.tracks if t.kind == "audio"]
    subtitles = [t for t in probe.tracks if t.kind == "subtitle"]
    if not videos and not item.prepared_variants: raise PipelineError(f"No video track detected: {source}")
    detected = item.source_quality or quality_from_height(videos[0].height if videos else None)
    targets = choose_targets(detected, item.target_qualities)
    prepared = item.prepared_variants or {}
    duration = probe.duration_seconds
    manifest: dict[str, Any] = {"schemaVersion": 1, "assetId": asset_id, "title": item.title, "contentType": item.content_type, "source": {"originalName": source.name, "container": probe.format_name, "quality": detected, "sizeBytes": probe.size_bytes, "archived": False}, "externalIds": {"imdb": item.imdb_id, "tmdb": item.tmdb_id}, "episode": {"season": item.season, "number": item.episode} if item.season is not None else None, "durationSeconds": duration, "playback": {"master": "master.m3u8", "qualities": [], "audio": [], "subtitles": []}, "tracks": [asdict(t) for t in probe.tracks], "createdAt": int(time.time())}
    for quality in targets:
        profile = QUALITY_PROFILES[quality]
        variant_source = Path(prepared.get(quality, source)).expanduser().resolve()
        if not variant_source.exists(): raise PipelineError(f"Prepared variant does not exist for {quality}: {variant_source}")
        folder = asset_dir / "video" / safe_slug(quality); folder.mkdir(parents=True, exist_ok=True)
        playlist, segment = folder / "index.m3u8", folder / "stream.m4s"
        scale = f"scale=-2:{profile['height']}:force_original_aspect_ratio=decrease:force_divisible_by=2"
        run(["ffmpeg", "-y", "-i", str(variant_source), "-map", "0:v:0", "-an", "-vf", scale, "-c:v", "libx264", "-preset", "medium", "-crf", str(profile["crf"]), "-maxrate", str(profile["maxrate"]), "-bufsize", str(profile["bufsize"]), "-pix_fmt", "yuv420p", "-g", "144", "-keyint_min", "144", "-sc_threshold", "0", "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4", "-hls_flags", "single_file+independent_segments", "-hls_fmp4_init_filename", f"init-{safe_slug(quality)}.mp4", "-hls_segment_filename", str(segment), str(playlist)])
        manifest["playback"]["qualities"].append({"name": quality, "width": profile["width"], "height": profile["height"], "bandwidth": profile["bandwidth"], "playlist": playlist.relative_to(asset_dir).as_posix()})
    for order, track in enumerate(audios):
        track_id = f"a{order:02d}-{safe_slug(track.language)}"; folder = asset_dir / "audio" / track_id; folder.mkdir(parents=True, exist_ok=True)
        playlist, segment = folder / "index.m3u8", folder / "stream.m4s"; bitrate = "384k" if (track.channels or 2) > 2 else "192k"
        run(["ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-vn", "-sn", "-c:a", "aac", "-b:a", bitrate, "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4", "-hls_flags", "single_file+independent_segments", "-hls_fmp4_init_filename", f"init-{track_id}.mp4", "-hls_segment_filename", str(segment), str(playlist)])
        manifest["playback"]["audio"].append({"id": track_id, "language": track.language, "name": track.title, "codec": "aac", "channels": track.channels, "default": track.default or order == 0, "playlist": playlist.relative_to(asset_dir).as_posix()})
    for order, track in enumerate(subtitles):
        track_id = f"s{order:02d}-{safe_slug(track.language)}"; folder = asset_dir / "subtitles" / track_id; folder.mkdir(parents=True, exist_ok=True)
        vtt, playlist = folder / "captions.vtt", folder / "index.m3u8"
        run(["ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-f", "webvtt", str(vtt)])
        playlist.write_text("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:{}\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:{:.3f},\ncaptions.vtt\n#EXT-X-ENDLIST\n".format(max(1, int(duration + .999)), duration), encoding="utf-8")
        manifest["playback"]["subtitles"].append({"id": track_id, "language": track.language, "name": track.title, "forced": track.forced, "default": track.default, "playlist": playlist.relative_to(asset_dir).as_posix()})
    write_master_manifest(asset_dir, manifest)
    (asset_dir / "asset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    enforce_folder_limits(asset_dir)
    return manifest

def write_master_manifest(asset_dir: Path, manifest: dict[str, Any]) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for audio in manifest["playback"]["audio"]:
        lines.append(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME={json.dumps(audio["name"])},LANGUAGE={json.dumps(audio["language"])},AUTOSELECT=YES,DEFAULT={"YES" if audio["default"] else "NO"},URI={json.dumps(audio["playlist"])}')
    for subtitle in manifest["playback"]["subtitles"]:
        lines.append(f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME={json.dumps(subtitle["name"])},LANGUAGE={json.dumps(subtitle["language"])},AUTOSELECT=YES,DEFAULT={"YES" if subtitle["default"] else "NO"},FORCED={"YES" if subtitle["forced"] else "NO"},URI={json.dumps(subtitle["playlist"])}')
    for quality in sorted(manifest["playback"]["qualities"], key=lambda q: q["height"]):
        attrs = [f"BANDWIDTH={quality['bandwidth']}", f"RESOLUTION={quality['width']}x{quality['height']}"]
        if manifest["playback"]["audio"]: attrs.append('AUDIO="audio"')
        if manifest["playback"]["subtitles"]: attrs.append('SUBTITLES="subs"')
        lines.extend(["#EXT-X-STREAM-INF:" + ",".join(attrs), quality["playlist"]])
    (asset_dir / "master.m3u8").write_text("\n".join(lines) + "\n", encoding="utf-8")

def enforce_folder_limits(root: Path, limit: int = FOLDER_FILE_LIMIT) -> None:
    violations = [f"{folder}: {len(files)} files" for folder, _, files in os.walk(root) if len(files) > limit]
    if violations: raise PipelineError("Folder safety limit exceeded (9000):\n" + "\n".join(violations))

def collect_uploads(output_root: Path) -> list[tuple[Path, str]]:
    return [(p, p.relative_to(output_root).as_posix()) for p in sorted(x for x in output_root.rglob("*") if x.is_file())]

def upload_huggingface(output_root: Path, repo_id: str, *, repo_type: str = "dataset", token: str | None = None, message: str, max_ops_per_commit: int = DEFAULT_MAX_OPS_PER_COMMIT, dry_run: bool = False) -> list[str]:
    uploads = collect_uploads(output_root)
    if not uploads: raise PipelineError("Nothing to upload")
    if dry_run:
        print(json.dumps({"repo": repo_id, "files": len(uploads), "commits": (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit}, indent=2)); return []
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError as exc:
        raise PipelineError("Install requirements: pip install -r tools/media_pipeline/requirements.txt") from exc
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    api = HfApi(token=token or os.getenv("HF_TOKEN")); urls: list[str] = []
    for start in range(0, len(uploads), max_ops_per_commit):
        chunk = uploads[start:start + max_ops_per_commit]
        operations = [CommitOperationAdd(path_in_repo=remote, path_or_fileobj=str(local)) for local, remote in chunk]
        total = (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit
        suffix = "" if total == 1 else f" ({start // max_ops_per_commit + 1}/{total})"
        result = api.create_commit(repo_id=repo_id, repo_type=repo_type, operations=operations, commit_message=message + suffix)
        urls.append(str(result.commit_url))
    return urls

def update_github_catalog(manifests: Sequence[dict[str, Any]], *, repository: str, token: str, branch: str = "main", path: str = "catalog/media/index.json") -> str:
    api_url = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    sha = None; current: dict[str, Any] = {"schemaVersion": 1, "assets": {}}
    try:
        with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers)) as response:
            payload = json.load(response); sha = payload.get("sha"); current = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 404: raise PipelineError(f"GitHub catalog read failed: {exc}") from exc
    assets = current.setdefault("assets", {})
    for manifest in manifests:
        assets[manifest["assetId"]] = {"title": manifest["title"], "contentType": manifest["contentType"], "externalIds": manifest.get("externalIds"), "episode": manifest.get("episode"), "hfPath": f"objects/{manifest['assetId'][:2]}/{manifest['assetId']}", "master": "master.m3u8", "qualities": [q["name"] for q in manifest["playback"]["qualities"]], "audio": manifest["playback"]["audio"], "subtitles": manifest["playback"]["subtitles"], "updatedAt": int(time.time())}
    body: dict[str, Any] = {"message": f"Catalog batch: {len(manifests)} media asset(s)", "content": base64.b64encode(json.dumps(current, ensure_ascii=False, indent=2).encode()).decode(), "branch": branch}
    if sha: body["sha"] = sha
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}", data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}, method="PUT")
    try:
        with urllib.request.urlopen(request) as response: payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise PipelineError(f"GitHub catalog update failed: {exc.code} {exc.read().decode(errors='replace')}") from exc
    return payload["commit"]["html_url"]

def tmdb_request(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {}); url = f"https://api.themoviedb.org/3/{path.lstrip('/')}" + (f"?{query}" if query else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "accept": "application/json"})) as response: return json.load(response)
    except urllib.error.HTTPError as exc: raise PipelineError(f"TMDB request failed: {exc.code} {exc.reason}") from exc

def fetch_metadata(*, title: str | None, imdb_id: str | None, token: str, language: str = "tr-TR") -> dict[str, Any]:
    if imdb_id:
        found = tmdb_request(f"find/{imdb_id}", token, {"external_source": "imdb_id", "language": language}); candidate = (found.get("movie_results") or found.get("tv_results") or [None])[0]
        if not candidate: raise PipelineError(f"No TMDB record found for IMDb id {imdb_id}")
        media_type = "movie" if found.get("movie_results") else "tv"; media_id = candidate["id"]
    elif title:
        found = tmdb_request("search/multi", token, {"query": title, "language": language, "include_adult": "false"}); candidates = [r for r in found.get("results", []) if r.get("media_type") in {"movie", "tv"}]
        if not candidates: raise PipelineError(f"No metadata found for {title}")
        candidate = candidates[0]; media_type, media_id = candidate["media_type"], candidate["id"]
    else: raise PipelineError("title or imdb_id is required")
    details = tmdb_request(f"{media_type}/{media_id}", token, {"language": language, "append_to_response": "images,external_ids,credits"})
    return {"provider": "tmdb", "tmdbId": media_id, "imdbId": (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id") or imdb_id, "type": media_type, "title": details.get("title") or details.get("name"), "originalTitle": details.get("original_title") or details.get("original_name"), "overview": details.get("overview"), "releaseDate": details.get("release_date") or details.get("first_air_date"), "runtime": details.get("runtime") or (details.get("episode_run_time") or [None])[0], "genres": [g["name"] for g in details.get("genres", [])], "posterPath": details.get("poster_path"), "backdropPath": details.get("backdrop_path"), "credits": [{"name": p.get("name"), "character": p.get("character")} for p in (details.get("credits") or {}).get("cast", [])[:20]], "raw": details}

def load_batch(path: Path) -> list[BatchItem]:
    payload = json.loads(path.read_text(encoding="utf-8")); values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list): raise PipelineError("Batch file must contain an items array")
    return [BatchItem(**value) for value in values]

def command_analyze(args: argparse.Namespace) -> None: print(json.dumps(asdict(ffprobe(Path(args.source))), ensure_ascii=False, indent=2))
def command_process(args: argparse.Namespace) -> None: print(json.dumps(process_item(BatchItem(source=args.source, title=args.title, content_type=args.type, source_quality=args.source_quality, target_qualities=args.qualities, imdb_id=args.imdb_id, season=args.season, episode=args.episode), Path(args.output), overwrite=args.overwrite), ensure_ascii=False, indent=2))
def command_batch(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True); manifests = [process_item(item, output, overwrite=args.overwrite) for item in load_batch(Path(args.config))]
    (output / "batch.json").write_text(json.dumps({"schemaVersion": 1, "assets": manifests}, ensure_ascii=False, indent=2), encoding="utf-8")
    hf_urls = upload_huggingface(output, args.hf_repo, repo_type=args.hf_repo_type, message=args.message, max_ops_per_commit=args.max_ops, dry_run=args.dry_run) if args.hf_repo else []
    github_url = None
    if args.github_repo and not args.dry_run:
        token = args.github_token or os.getenv("GITHUB_TOKEN")
        if not token: raise PipelineError("GITHUB_TOKEN is required for catalog update")
        github_url = update_github_catalog(manifests, repository=args.github_repo, token=token, branch=args.github_branch)
    print(json.dumps({"assets": len(manifests), "files": len(collect_uploads(output)), "hfCommits": hf_urls, "githubCommit": github_url}, ensure_ascii=False, indent=2))
def command_metadata(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("TMDB_API_TOKEN")
    if not token: raise PipelineError("TMDB_API_TOKEN is required")
    print(json.dumps(fetch_metadata(title=args.title, imdb_id=args.imdb_id, token=token, language=args.language), ensure_ascii=False, indent=2))
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="odium-media"); sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze"); analyze.add_argument("source"); analyze.set_defaults(func=command_analyze)
    process = sub.add_parser("process"); process.add_argument("source"); process.add_argument("--title", required=True); process.add_argument("--type", default="movie"); process.add_argument("--source-quality", choices=QUALITY_PROFILES); process.add_argument("--qualities", nargs="+", choices=QUALITY_PROFILES); process.add_argument("--imdb-id"); process.add_argument("--season", type=int); process.add_argument("--episode", type=int); process.add_argument("--output", default="build/media"); process.add_argument("--overwrite", action="store_true"); process.set_defaults(func=command_process)
    batch = sub.add_parser("batch"); batch.add_argument("config"); batch.add_argument("--output", default="build/media"); batch.add_argument("--hf-repo"); batch.add_argument("--hf-repo-type", default="dataset", choices=["dataset", "model", "space"]); batch.add_argument("--github-repo"); batch.add_argument("--github-branch", default="main"); batch.add_argument("--github-token"); batch.add_argument("--message", default="OdiumFlix batch upload"); batch.add_argument("--max-ops", type=int, default=DEFAULT_MAX_OPS_PER_COMMIT); batch.add_argument("--overwrite", action="store_true"); batch.add_argument("--dry-run", action="store_true"); batch.set_defaults(func=command_batch)
    metadata = sub.add_parser("metadata"); metadata.add_argument("--title"); metadata.add_argument("--imdb-id"); metadata.add_argument("--token"); metadata.add_argument("--language", default="tr-TR"); metadata.set_defaults(func=command_metadata)
    return parser
def main() -> int:
    try: args = build_parser().parse_args(); args.func(args); return 0
    except PipelineError as exc: print(f"error: {exc}", file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
