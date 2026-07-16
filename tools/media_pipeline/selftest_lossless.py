#!/usr/bin/env python3
"""Fast end-to-end self-test for OdiumFlix lossless packaging."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from odium_media import BatchItem, ffprobe, process_item


def command(name: str) -> str:
    env = "ODIUM_FFMPEG" if name == "ffmpeg" else "ODIUM_FFPROBE"
    return os.getenv(env, name)


def run(args: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(args, check=True, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE)
    return result.stdout or ""


def stream_hash(input_path: str) -> str:
    return run([command("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", input_path, "-map", "0:v:0", "-c", "copy", "-f", "hash", "-hash", "md5", "-"], capture=True).strip()


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="odiumflix-lossless-test-"))
    try:
        subtitle = root / "caption.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\nMerhaba Łódź!\n", encoding="utf-8")
        source = root / "source.mkv"
        run([
            command("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1.5",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1.5",
            "-i", str(subtitle), "-map", "0:v", "-map", "1:a", "-map", "2:s",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-c:s", "srt", str(source),
        ])
        output = root / "out"
        manifest = process_item(
            BatchItem(
                source=str(source), title="Kayıpsız Test", source_quality="2160p",
                target_qualities=["2160p", "1080p", "720p"], video_codec="h264",
                audio_codec="copy", processing_mode="split",
            ),
            output, overwrite=True,
        )
        qualities = manifest["playback"]["qualities"]
        assert [quality["name"] for quality in qualities] == ["2160p"], qualities
        assert qualities[0]["actualWidth"] == 320 and qualities[0]["actualHeight"] == 180
        assert qualities[0]["losslessCopy"] is True
        assert manifest["playback"]["audio"][0]["losslessCopy"] is True
        assert any("yok sayıldı" in warning for warning in manifest["warnings"])
        asset = output / "objects" / manifest["assetId"][:2] / manifest["assetId"]
        assert stream_hash(str(source)) == stream_hash(str(asset / qualities[0]["playlist"]))
        assert ffprobe(source).tracks[0].codec == qualities[0]["codec"]
        json.loads((asset / "asset.json").read_text(encoding="utf-8"))
        print("LOSSLESS_SELFTEST_OK")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
