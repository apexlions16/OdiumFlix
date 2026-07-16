#!/usr/bin/env python3
"""OdiumFlix LAN/remote worker API for mobile Studio."""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from odium_media import (
    BatchItem,
    QUALITY_PROFILES,
    configure_utf8_console,
    huggingface_base_url,
    process_item,
    update_asset_files,
    update_github_catalog,
    upload_huggingface,
)

configure_utf8_console()
app = FastAPI(title="OdiumFlix Media Worker", version="0.3.0-alpha.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict[str, Any]] = {}
ROOT = Path(os.getenv("ODIUM_WORKER_ROOT", Path.home() / "OdiumFlixWorker")).resolve()


class JobView(BaseModel):
    id: str
    status: str
    progress: int
    message: str
    createdAt: int
    result: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.3.0-alpha.2",
        "folderFileLimit": 9000,
        "maxOperationsPerCommit": 100,
        "xet": True,
        "localFirst": True,
        "videoPolicy": "lossless-stream-copy-only",
        "time": int(time.time()),
    }


@app.get("/v1/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    return JOBS[job_id]


async def save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := await upload.read(8 * 1024 * 1024):
            output.write(chunk)
    await upload.close()


@app.post("/v1/batches", response_model=JobView)
async def create_batch(
    background: BackgroundTasks,
    plan: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    try:
        payload = json.loads(plan)
        items = payload["items"]
        settings = payload.get("settings") or {}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(400, "Invalid batch plan") from exc
    if len(items) != len(files):
        raise HTTPException(400, "Plan item count and file count differ")

    job_id = uuid.uuid4().hex
    incoming = ROOT / "incoming" / job_id
    for index, upload in enumerate(files):
        destination = incoming / f"{index:04d}-{Path(upload.filename or 'media.bin').name}"
        await save_upload(upload, destination)
        items[index]["source"] = str(destination)
    (incoming / "plan.json").write_text(
        json.dumps({"schemaVersion": 3, "items": items, "settings": settings}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "message": "Batch sıraya alındı",
        "createdAt": int(time.time()),
        "result": None,
    }
    background.add_task(run_job, job_id, items, settings)
    return JOBS[job_id]


def merge_prepared_items(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    singles: list[dict[str, Any]] = []
    for original in values:
        value = dict(original)
        key = value.pop("group_key", None)
        quality = value.get("source_quality") or "1080p"
        # Compatibility fields are normalized to the one supplied quality.
        value["target_qualities"] = [quality]
        value["video_codec"] = "copy"
        value.setdefault("audio_codec", "copy")
        if not key:
            singles.append(value)
            continue
        source = value["source"]
        current = grouped.get(key)
        if current is None:
            value["prepared_variants"] = {quality: source}
            grouped[key] = value
            continue
        current.setdefault("prepared_variants", {})[quality] = source
        current["target_qualities"] = list(current["prepared_variants"].keys())
        current["external_audio"] = list(dict.fromkeys([
            *(current.get("external_audio") or []),
            *(value.get("external_audio") or []),
        ]))
        current["external_subtitles"] = list(dict.fromkeys([
            *(current.get("external_subtitles") or []),
            *(value.get("external_subtitles") or []),
        ]))
        current["keep_original"] = bool(current.get("keep_original") or value.get("keep_original"))
        current_height = QUALITY_PROFILES.get(current.get("source_quality") or "", {}).get("height", 0)
        new_height = QUALITY_PROFILES.get(quality, {}).get("height", 0)
        if new_height > current_height:
            current["source"] = source
            current["source_quality"] = quality
    return [*singles, *grouped.values()]


def setting(settings: dict[str, Any], camel: str, env: str, default: Any = None) -> Any:
    value = settings.get(camel)
    return value if value not in (None, "") else os.getenv(env, default)


def run_job(job_id: str, raw_values: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    values = merge_prepared_items(raw_values)
    output = ROOT / "processed" / job_id
    try:
        JOBS[job_id].update(status="processing", progress=5, message="Kayıpsız yerel medya analizi başladı")
        tmdb_token = setting(settings, "tmdbToken", "TMDB_API_TOKEN")
        metadata_language = settings.get("metadataLanguage") or "tr-TR"
        manifests: list[dict[str, Any]] = []
        for index, value in enumerate(values):
            manifests.append(
                process_item(
                    BatchItem(**value),
                    output,
                    overwrite=True,
                    tmdb_token=tmdb_token,
                    metadata_language=metadata_language,
                )
            )
            JOBS[job_id].update(
                progress=5 + int(68 * (index + 1) / max(1, len(values))),
                message=f"{index + 1}/{len(values)} medya kalite değişmeden işlendi",
            )

        hf_repo = setting(settings, "hfRepo", "HF_REPO_ID")
        hf_repo_type = settings.get("hfRepoType") or os.getenv("HF_REPO_TYPE", "dataset")
        hf_private = bool(settings.get("hfPrivate", False))
        hf_token = setting(settings, "hfToken", "HF_TOKEN")
        hf_commits: list[str] = []
        storage: dict[str, Any] | None = None
        if hf_repo:
            storage = {
                "provider": "huggingface",
                "repoId": hf_repo,
                "repoType": hf_repo_type,
                "revision": "main",
                "baseUrl": huggingface_base_url(hf_repo, hf_repo_type),
                "private": hf_private,
            }
            update_asset_files(output, manifests, storage)
            JOBS[job_id].update(status="uploading", progress=78, message="Hugging Face Xet batch hazırlanıyor")
            hf_commits = upload_huggingface(
                output,
                hf_repo,
                repo_type=hf_repo_type,
                token=hf_token,
                private=hf_private,
                message=f"OdiumFlix lossless mobile batch {job_id}",
            )

        github_repo = setting(settings, "githubRepo", "ODIUM_GITHUB_REPO")
        github_token = setting(settings, "githubToken", "GITHUB_TOKEN")
        github_branch = settings.get("githubBranch") or "main"
        github_commit = None
        if github_repo and github_token:
            JOBS[job_id].update(progress=94, message="GitHub gerçek kataloğu güncelleniyor")
            github_commit = update_github_catalog(
                manifests,
                repository=github_repo,
                token=github_token,
                branch=github_branch,
            )

        warnings = [warning for manifest in manifests for warning in manifest.get("warnings", [])]
        JOBS[job_id].update(
            status="completed",
            progress=100,
            message="Batch tamamlandı" if not warnings else f"Batch tamamlandı ({len(warnings)} uyarı)",
            result={
                "assets": len(manifests),
                "hfCommits": hf_commits,
                "githubCommit": github_commit,
                "storage": storage,
                "output": str(output),
                "warnings": warnings,
            },
        )
    except Exception as exc:  # worker jobs must preserve error details
        JOBS[job_id].update(status="failed", message=str(exc), result=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
