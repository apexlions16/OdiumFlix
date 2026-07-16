from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from media_common import PipelineError, ProbeResult, Track, run, run_soft, safe_slug

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
    "aac": ".aac", "mp2": ".mp2", "mp3": ".mp3", "ac3": ".ac3", "eac3": ".eac3",
    "opus": ".opus", "vorbis": ".ogg", "flac": ".flac", "alac": ".m4a",
    "truehd": ".thd", "mlp": ".mlp", "dts": ".dts", "dca": ".dts",
    "pcm_s16le": ".wav", "pcm_s24le": ".wav", "pcm_s32le": ".wav",
    "pcm_f32le": ".wav", "pcm_f64le": ".wav", "wavpack": ".wv", "ape": ".ape",
    "amr_nb": ".amr", "amr_wb": ".amr", "tta": ".tta", "tak": ".tak",
}
SUBTITLE_EXTENSIONS = {
    "subrip": ".srt", "srt": ".srt", "webvtt": ".vtt", "ass": ".ass", "ssa": ".ssa",
    "hdmv_pgs_subtitle": ".sup", "dvd_subtitle": ".sub", "dvb_subtitle": ".sub",
    "mov_text": ".srt", "sami": ".smi", "ttml": ".ttml",
}


def write_single_file_playlist(path: Path, filename: str, duration: float) -> None:
    path.write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n"
        f"#EXT-X-TARGETDURATION:{max(1, int(duration + .999))}\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:{duration:.3f},\n{filename}\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )


def _clean_hls_files(folder: Path) -> None:
    for pattern in ("*.m3u8", "*.m4s", "*.mp4", "*.ts"):
        for file in folder.glob(pattern):
            file.unlink(missing_ok=True)


def _normalize_playlist_paths(playlist: Path, folder: Path) -> None:
    if not playlist.exists():
        return
    text = playlist.read_text(encoding="utf-8", errors="replace")
    prefixes = {str(folder.resolve()).replace("\\", "/") + "/", str(folder).replace("\\", "/") + "/"}
    normalized = text.replace("\\", "/")
    for prefix in prefixes:
        normalized = normalized.replace(prefix, "")
    playlist.write_text(normalized, encoding="utf-8")


def package_video_lossless(source: Path, folder: Path, label: str, probe: ProbeResult) -> dict[str, Any]:
    videos = [track for track in probe.tracks if track.kind == "video"]
    if not videos:
        raise PipelineError(f"Video parçası bulunamadı: {source}")
    track = videos[0]
    folder.mkdir(parents=True, exist_ok=True)
    playlist = folder / "video.m3u8"
    fmp4_segment = folder / "video.m4s"
    fmp4_command = [
        "ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-an", "-sn", "-dn",
        "-c:v", "copy", "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
        "-hls_segment_type", "fmp4", "-hls_flags", "single_file+independent_segments",
        "-hls_fmp4_init_filename", "video-init.mp4", "-hls_segment_filename", str(fmp4_segment), str(playlist),
    ]
    ok, detail = run_soft(fmp4_command)
    packaging = "hls-fmp4-stream-copy"

    if not ok:
        _clean_hls_files(folder)
        ts_segment = folder / "video-%05d.ts"
        ok, ts_detail = run_soft([
            "ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-an", "-sn", "-dn",
            "-c:v", "copy", "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments", "-hls_segment_filename", str(ts_segment), str(playlist),
        ])
        if ok:
            packaging = "hls-mpegts-stream-copy"
            detail = detail[-900:] + "\nFMP4 desteklenmedi; MPEG-TS HLS kullanıldı."
        else:
            detail = detail[-900:] + "\n" + ts_detail[-900:]

    if ok:
        _normalize_playlist_paths(playlist, folder)

    direct_file: Path | None = None
    if not ok:
        _clean_hls_files(folder)
        direct_file = folder / "video-only.mkv"
        run(["ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-an", "-sn", "-dn", "-c:v", "copy", str(direct_file)])
        packaging = "video-only-mkv-stream-copy"

    asset_root = folder.parent.parent
    return {
        "name": label, "declaredQuality": label,
        "actualWidth": track.width, "actualHeight": track.height,
        "codec": track.codec, "bitRate": track.bit_rate, "sourceName": source.name,
        "packaging": packaging, "losslessCopy": True,
        "playlist": playlist.relative_to(asset_root).as_posix() if ok else None,
        "file": direct_file.relative_to(asset_root).as_posix() if direct_file else None,
        "packagingWarning": None if ok and packaging == "hls-fmp4-stream-copy" else detail[-2000:],
    }


def copy_direct(source: Path, folder: Path, label: str, probe: ProbeResult) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"source{source.suffix.lower() or '.mkv'}"
    shutil.copy2(source, destination)
    video = next((track for track in probe.tracks if track.kind == "video"), None)
    asset_root = folder.parent.parent
    return {
        "name": label, "declaredQuality": label,
        "actualWidth": video.width if video else None, "actualHeight": video.height if video else None,
        "codec": video.codec if video else None, "sourceName": source.name,
        "packaging": "direct-original-container", "losslessCopy": True,
        "playlist": None, "file": destination.relative_to(asset_root).as_posix(),
    }


def audio_extension(source_codec: str, selected_codec: str) -> str:
    if selected_codec == "copy":
        return COPY_AUDIO_EXTENSIONS.get(source_codec, ".mka")
    if selected_codec not in AUDIO_ENCODERS:
        raise PipelineError(f"Desteklenmeyen ses kodeği: {selected_codec}")
    return AUDIO_ENCODERS[selected_codec]["extension"]


def extract_audio_track(source: Path, track: Track, folder: Path, selected_codec: str, order: int) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    extension = audio_extension(track.codec, selected_codec)
    output = folder / f"audio{extension}"
    codec_args = ["-c:a", "copy"] if selected_codec == "copy" else ["-c:a", AUDIO_ENCODERS[selected_codec]["encoder"]]
    if selected_codec == "aac":
        codec_args += ["-b:a", "384k" if (track.channels or 2) > 2 else "192k"]
    try:
        run(["ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-vn", "-sn", *codec_args, str(output)])
    except PipelineError:
        if selected_codec != "copy" or extension == ".mka":
            raise
        output = folder / "audio.mka"
        run(["ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-vn", "-sn", "-c:a", "copy", str(output)])

    playlist: Path | None = None
    warning: str | None = None
    effective_codec = track.codec if selected_codec == "copy" else selected_codec
    if effective_codec in {"aac", "ac3", "eac3", "mp3"}:
        playlist = folder / "audio.m3u8"
        segment = folder / "audio.m4s"
        ok, detail = run_soft([
            "ffmpeg", "-y", "-i", str(source), "-map", f"0:{track.index}", "-vn", "-sn", *codec_args,
            "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4",
            "-hls_flags", "single_file", "-hls_fmp4_init_filename", "audio-init.mp4", "-hls_segment_filename", str(segment), str(playlist),
        ])
        if not ok:
            playlist = None
            warning = detail[-1500:]
        else:
            _normalize_playlist_paths(playlist, folder)

    asset_root = folder.parent.parent
    return {
        "id": f"a{order:02d}-{safe_slug(track.language)}", "language": track.language,
        "name": track.title, "sourceCodec": track.codec, "codec": effective_codec,
        "channels": track.channels, "channelLayout": track.channel_layout,
        "default": track.default or order == 0, "losslessCopy": selected_codec == "copy",
        "file": output.relative_to(asset_root).as_posix(),
        "playlist": playlist.relative_to(asset_root).as_posix() if playlist else None,
        "packagingWarning": warning,
    }


def add_subtitle(source: Path, track: Track, folder: Path, duration: float, order: int, *, external: bool, keep_original: bool) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    asset_root = folder.parent.parent
    vtt = folder / "subtitles.vtt"
    playlist = folder / "subtitles.m3u8"
    map_args = ["-map", "0:s:0"] if external else ["-map", f"0:{track.index}"]
    ok, detail = run_soft(["ffmpeg", "-y", "-i", str(source), *map_args, "-f", "webvtt", str(vtt)])
    if ok:
        write_single_file_playlist(playlist, vtt.name, duration)
    original: Path | None = None
    if keep_original:
        if external:
            original = folder / f"original{source.suffix.lower() or '.sub'}"
            shutil.copy2(source, original)
        else:
            original = folder / f"original{SUBTITLE_EXTENSIONS.get(track.codec, '.mks')}"
            copy_ok, _ = run_soft(["ffmpeg", "-y", "-i", str(source), *map_args, "-c:s", "copy", str(original)])
            if not copy_ok:
                original = folder / "original.mks"
                copy_ok, _ = run_soft(["ffmpeg", "-y", "-i", str(source), *map_args, "-c:s", "copy", str(original)])
                if not copy_ok:
                    original = None
    return {
        "id": f"s{order:02d}-{safe_slug(track.language)}", "language": track.language,
        "name": track.title, "codec": track.codec, "forced": track.forced, "default": track.default,
        "playlist": playlist.relative_to(asset_root).as_posix() if ok else None,
        "file": vtt.relative_to(asset_root).as_posix() if ok else None,
        "original": original.relative_to(asset_root).as_posix() if original else None,
        "conversionWarning": None if ok else detail[-1500:],
    }
