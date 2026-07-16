#!/usr/bin/env python3
"""OdiumFlix lossless local media worker and transactional uploader."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from media_common import (
    BatchItem, DEFAULT_MAX_OPS_PER_COMMIT, PipelineError, QUALITY_PROFILES,
    collect_uploads, configure_utf8_console, emit_json, ffprobe, run_soft, write_console,
)
from media_metadata import fetch_metadata
from media_packaging import AUDIO_ENCODERS
from media_process import process_item
from media_remote import huggingface_base_url, update_asset_files, update_github_catalog, upload_huggingface


def load_batch(path: Path) -> list[BatchItem]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Batch dosyası bulunamadı: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Batch JSON okunamadı: {path} ({exc})") from exc
    values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise PipelineError("Batch dosyasında 'items' dizisi bulunmalı.")
    items: list[BatchItem] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise PipelineError(f"Batch öğesi {index} bir nesne değil.")
        try:
            items.append(BatchItem(**value))
        except TypeError as exc:
            raise PipelineError(f"Batch öğesi {index} geçersiz: {exc}") from exc
    return items


def command_analyze(args: argparse.Namespace) -> None:
    emit_json(asdict(ffprobe(Path(args.source).expanduser().resolve())))


def command_process(args: argparse.Namespace) -> None:
    item = BatchItem(
        source=args.source, title=args.title, content_type=args.type,
        source_quality=args.source_quality, target_qualities=args.qualities,
        imdb_id=args.imdb_id, imdb_url=args.imdb_url,
        season=args.season, episode=args.episode,
        processing_mode=args.processing_mode, keep_original=args.keep_original,
        video_codec="copy", audio_codec=args.audio_codec,
        external_audio=args.external_audio or [], external_subtitles=args.external_subtitles or [],
        keep_subtitle_originals=not args.discard_subtitle_originals,
    )
    manifest = process_item(
        item, Path(args.output).expanduser().resolve(), overwrite=args.overwrite,
        tmdb_token=args.tmdb_token or os.getenv("TMDB_API_TOKEN"),
        metadata_language=args.metadata_language,
    )
    emit_json(manifest)


def command_batch(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    tmdb_token = args.tmdb_token or os.getenv("TMDB_API_TOKEN")
    manifests = [
        process_item(item, output, overwrite=args.overwrite, tmdb_token=tmdb_token, metadata_language=args.metadata_language)
        for item in load_batch(Path(args.config).expanduser().resolve())
    ]

    storage: dict[str, Any] | None = None
    hf_urls: list[str] = []
    if args.hf_repo:
        storage = {
            "provider": "huggingface", "repoId": args.hf_repo, "repoType": args.hf_repo_type,
            "revision": "main", "baseUrl": huggingface_base_url(args.hf_repo, args.hf_repo_type),
            "private": args.hf_private,
        }
        update_asset_files(output, manifests, storage)
        hf_urls = upload_huggingface(
            output, args.hf_repo, repo_type=args.hf_repo_type,
            token=args.hf_token or os.getenv("HF_TOKEN"), private=args.hf_private,
            message=args.message, max_ops_per_commit=args.max_ops, dry_run=args.dry_run,
        )

    github_url = None
    if args.github_repo and not args.dry_run:
        github_token = args.github_token or os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise PipelineError("GitHub katalog güncellemesi için GITHUB_TOKEN gerekli.")
        github_url = update_github_catalog(
            manifests, repository=args.github_repo, token=github_token, branch=args.github_branch,
        )

    (output / "batch.json").write_text(
        json.dumps({"schemaVersion": 3, "assets": manifests, "storage": storage}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    warnings = [warning for manifest in manifests for warning in manifest.get("warnings", [])]
    emit_json({
        "assets": len(manifests), "files": len(collect_uploads(output)),
        "hfCommits": hf_urls, "githubCommit": github_url, "storage": storage,
        "warnings": warnings, "output": str(output),
    })


def command_metadata(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("TMDB_API_TOKEN")
    if not token:
        raise PipelineError("TMDB API Read Access Token veya v3 API Key gerekli.")
    from media_common import parse_imdb_id
    imdb_id = parse_imdb_id(args.imdb_id or args.imdb_url)
    emit_json(fetch_metadata(title=args.title, imdb_id=imdb_id, token=token, language=args.language))


def command_diagnostics(args: argparse.Namespace) -> None:
    checks: dict[str, Any] = {"version": "0.3.0-alpha.2", "utf8": True, "videoPolicy": "lossless-stream-copy-only"}
    for name in ("ffmpeg", "ffprobe"):
        ok, detail = run_soft([name, "-version"])
        checks[name] = {
            "ok": ok,
            "path": os.getenv("ODIUM_FFMPEG" if name == "ffmpeg" else "ODIUM_FFPROBE", name),
            "detail": detail.splitlines()[0] if detail else "",
        }
    if args.tmdb_token:
        try:
            from media_metadata import tmdb_request
            tmdb_request("configuration", args.tmdb_token)
            checks["tmdb"] = {"ok": True}
        except PipelineError as exc:
            checks["tmdb"] = {"ok": False, "detail": str(exc)}
    emit_json(checks)
    if not checks["ffmpeg"]["ok"] or not checks["ffprobe"]["ok"]:
        raise PipelineError("Medya araçları doğrulanamadı.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="odium-media", description="OdiumFlix kayıpsız medya işleyici")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze")
    analyze.add_argument("source")
    analyze.set_defaults(func=command_analyze)

    process = sub.add_parser("process")
    process.add_argument("source")
    process.add_argument("--title", required=True)
    process.add_argument("--type", default="movie")
    process.add_argument("--source-quality", choices=QUALITY_PROFILES)
    process.add_argument("--qualities", nargs="+", choices=QUALITY_PROFILES, help="Eski uyumluluk alanı; alt kalite üretmez")
    process.add_argument("--imdb-id")
    process.add_argument("--imdb-url")
    process.add_argument("--season", type=int)
    process.add_argument("--episode", type=int)
    process.add_argument("--processing-mode", choices=["auto", "split", "direct"], default="auto")
    process.add_argument("--audio-codec", choices=["copy", *AUDIO_ENCODERS], default="copy")
    process.add_argument("--external-audio", nargs="*")
    process.add_argument("--external-subtitles", nargs="*")
    process.add_argument("--discard-subtitle-originals", action="store_true")
    process.add_argument("--keep-original", action="store_true")
    process.add_argument("--tmdb-token")
    process.add_argument("--metadata-language", default="tr-TR")
    process.add_argument("--output", default="build/media")
    process.add_argument("--overwrite", action="store_true")
    process.set_defaults(func=command_process)

    batch = sub.add_parser("batch")
    batch.add_argument("config")
    batch.add_argument("--output", default="build/media")
    batch.add_argument("--hf-repo")
    batch.add_argument("--hf-repo-type", default="dataset", choices=["dataset", "model", "space"])
    batch.add_argument("--hf-private", action="store_true")
    batch.add_argument("--hf-token")
    batch.add_argument("--github-repo")
    batch.add_argument("--github-branch", default="main")
    batch.add_argument("--github-token")
    batch.add_argument("--tmdb-token")
    batch.add_argument("--metadata-language", default="tr-TR")
    batch.add_argument("--message", default="OdiumFlix lossless batch upload")
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

    diagnostics = sub.add_parser("diagnostics")
    diagnostics.add_argument("--tmdb-token")
    diagnostics.set_defaults(func=command_diagnostics)
    return parser


def main() -> int:
    configure_utf8_console()
    try:
        args = build_parser().parse_args()
        args.func(args)
        return 0
    except PipelineError as exc:
        write_console(f"error: {exc}", error=True)
        return 2
    except KeyboardInterrupt:
        write_console("error: İşlem kullanıcı tarafından durduruldu.", error=True)
        return 130
    except Exception as exc:
        write_console(f"error: Beklenmeyen hata: {type(exc).__name__}: {exc}", error=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
