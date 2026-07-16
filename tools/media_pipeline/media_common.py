from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

FOLDER_FILE_LIMIT = 9000
DEFAULT_MAX_OPS_PER_COMMIT = 100
QUALITY_PROFILES: dict[str, dict[str, int]] = {
    "2160p": {"width": 3840, "height": 2160},
    "1440p": {"width": 2560, "height": 1440},
    "1080p+": {"width": 1920, "height": 1080},
    "1080p": {"width": 1920, "height": 1080},
    "720p": {"width": 1280, "height": 720},
    "480p": {"width": 854, "height": 480},
}
QUALITY_ORDER = tuple(QUALITY_PROFILES)


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
    bit_rate: int | None = None
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
    target_qualities: list[str] | None = None  # legacy, intentionally ignored
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
    video_codec: str = "copy"  # compatibility field; video is always copied
    audio_codec: str = "copy"
    external_audio: list[str] = field(default_factory=list)
    external_subtitles: list[str] = field(default_factory=list)
    keep_subtitle_originals: bool = True
    trailer_url: str | None = None


def configure_utf8_console() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def write_console(text: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    text = text if text.endswith("\n") else text + "\n"
    try:
        stream.write(text)
        stream.flush()
    except UnicodeEncodeError:
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write(text.encode("utf-8", "replace"))
            buffer.flush()


def emit_json(value: Any) -> None:
    write_console(json.dumps(value, ensure_ascii=False, indent=2))


def executable(name: str) -> str:
    env_name = "ODIUM_FFMPEG" if name == "ffmpeg" else "ODIUM_FFPROBE"
    return os.getenv(env_name, name).strip().strip('"') or name


def run(command: Sequence[str], *, capture: bool = False) -> str:
    resolved = list(command)
    if resolved and resolved[0] in {"ffmpeg", "ffprobe"}:
        resolved[0] = executable(resolved[0])
    try:
        result = subprocess.run(
            resolved,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise PipelineError(
            f"Gerekli medya aracı bulunamadı: {resolved[0]}. "
            "OdiumFlix Studio alpha.2 veya daha yeni sürümü temiz kur."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PipelineError(f"Komut başarısız ({exc.returncode}): {' '.join(command)}\n{detail}") from exc
    return result.stdout or ""


def run_soft(command: Sequence[str]) -> tuple[bool, str]:
    try:
        return True, run(command, capture=True)
    except PipelineError as exc:
        return False, str(exc)


def normalize_language(value: Any) -> str:
    language = str(value or "und").lower().strip()
    aliases = {
        "tur": "tr", "eng": "en", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr",
        "spa": "es", "ita": "it", "jpn": "ja", "kor": "ko", "por": "pt", "rus": "ru",
        "ara": "ar", "chi": "zh", "zho": "zh", "dut": "nl", "nld": "nl",
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
    if not path.exists():
        raise PipelineError(f"Dosya bulunamadı: {path}")
    raw = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"ffprobe çıktısı okunamadı: {path}") from exc
    tracks: list[Track] = []
    for stream in data.get("streams", []):
        kind = stream.get("codec_type", "unknown")
        if kind not in {"video", "audio", "subtitle"}:
            continue
        tags = stream.get("tags") or {}
        disposition = stream.get("disposition") or {}
        language = normalize_language(tags.get("language"))
        bit_rate = stream.get("bit_rate")
        tracks.append(Track(
            index=int(stream["index"]), kind=kind,
            codec=str(stream.get("codec_name") or "unknown"), language=language,
            title=str(tags.get("title") or default_track_title(kind, language, stream)).strip(),
            channels=int(stream["channels"]) if stream.get("channels") else None,
            channel_layout=stream.get("channel_layout"),
            width=int(stream["width"]) if stream.get("width") else None,
            height=int(stream["height"]) if stream.get("height") else None,
            bit_rate=int(bit_rate) if bit_rate and str(bit_rate).isdigit() else None,
            default=bool(disposition.get("default")), forced=bool(disposition.get("forced")),
        ))
    fmt = data.get("format") or {}
    return ProbeResult(
        path=str(path.resolve()), duration_seconds=float(fmt.get("duration") or 0),
        format_name=str(fmt.get("format_name") or path.suffix.lstrip(".")),
        size_bytes=int(fmt.get("size") or path.stat().st_size), tracks=tracks,
    )


def safe_slug(value: str) -> str:
    value = value.strip().lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "untitled"


def opaque_asset_id() -> str:
    import uuid
    return uuid.uuid4().hex


def parse_imdb_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b(tt\d{5,12})\b", value, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def quality_from_height(height: int | None) -> str:
    if not height:
        return "unknown"
    if height >= 2160: return "2160p"
    if height >= 1440: return "1440p"
    if height >= 1080: return "1080p"
    if height >= 720: return "720p"
    return "480p"


def quality_rank(label: str) -> int:
    try:
        return len(QUALITY_ORDER) - QUALITY_ORDER.index(label)
    except ValueError:
        match = re.search(r"(\d{3,4})", label)
        return int(match.group(1)) if match else 0


def enforce_folder_limits(root: Path, limit: int = FOLDER_FILE_LIMIT) -> None:
    violations = [f"{folder}: {len(files)} dosya" for folder, _, files in os.walk(root) if len(files) > limit]
    if violations:
        raise PipelineError("Klasör güvenlik sınırı aşıldı (9000):\n" + "\n".join(violations))


def collect_uploads(output_root: Path) -> list[tuple[Path, str]]:
    return [(p, p.relative_to(output_root).as_posix()) for p in sorted(output_root.rglob("*")) if p.is_file()]


def track_dicts(probe: ProbeResult) -> list[dict[str, Any]]:
    return [asdict(track) for track in probe.tracks]
