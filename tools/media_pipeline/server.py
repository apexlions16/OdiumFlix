#!/usr/bin/env python3
"""LAN/remote worker API for OdiumFlix mobile Studio."""
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

from odium_media import BatchItem, process_item, update_github_catalog, upload_huggingface

app = FastAPI(title="OdiumFlix Media Worker", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
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
    return {"ok": True, "folderFileLimit": 9000, "xet": True, "time": int(time.time())}

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
async def create_batch(background: BackgroundTasks, plan: str = Form(...), files: list[UploadFile] = File(...)) -> dict[str, Any]:
    try:
        payload = json.loads(plan)
        items = payload["items"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(400, "Invalid batch plan") from exc
    if len(items) != len(files):
        raise HTTPException(400, "Plan item count and file count differ")
    job_id = uuid.uuid4().hex
    incoming = ROOT / "incoming" / job_id
    for index, upload in enumerate(files):
        safe_name = f"{index:04d}-{Path(upload.filename or 'media.bin').name}"
        destination = incoming / safe_name
        await save_upload(upload, destination)
        items[index]["source"] = str(destination)
    (incoming / "plan.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Batch sıraya alındı", "createdAt": int(time.time()), "result": None}
    background.add_task(run_job, job_id, items)
    return JOBS[job_id]

def run_job(job_id: str, values: list[dict[str, Any]]) -> None:
    output = ROOT / "processed" / job_id
    try:
        JOBS[job_id].update(status="processing", progress=5, message="Medya analizi başladı")
        manifests = []
        for index, value in enumerate(values):
            manifests.append(process_item(BatchItem(**value), output, overwrite=True))
            JOBS[job_id].update(progress=5 + int(70 * (index + 1) / len(values)), message=f"{index + 1}/{len(values)} medya işlendi")
        hf_commits: list[str] = []
        hf_repo = os.getenv("HF_REPO_ID")
        if hf_repo:
            JOBS[job_id].update(status="uploading", progress=80, message="Hugging Face batch commit hazırlanıyor")
            hf_commits = upload_huggingface(output, hf_repo, repo_type=os.getenv("HF_REPO_TYPE", "dataset"), message=f"OdiumFlix mobile batch {job_id}")
        github_commit = None
        github_repo = os.getenv("ODIUM_GITHUB_REPO")
        github_token = os.getenv("GITHUB_TOKEN")
        if github_repo and github_token:
            JOBS[job_id].update(progress=94, message="GitHub kataloğu güncelleniyor")
            github_commit = update_github_catalog(manifests, repository=github_repo, token=github_token)
        JOBS[job_id].update(status="completed", progress=100, message="Batch tamamlandı", result={"assets": len(manifests), "hfCommits": hf_commits, "githubCommit": github_commit, "output": str(output)})
    except Exception as exc:
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
