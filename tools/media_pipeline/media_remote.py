from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from media_common import DEFAULT_MAX_OPS_PER_COMMIT, PipelineError, collect_uploads, emit_json


def huggingface_base_url(repo_id: str, repo_type: str) -> str:
    prefix = "datasets/" if repo_type == "dataset" else "spaces/" if repo_type == "space" else ""
    return f"https://huggingface.co/{prefix}{repo_id}/resolve/main"


def ensure_huggingface_repo(api: Any, repo_id: str, repo_type: str, private: bool) -> None:
    try:
        api.create_repo(repo_id=repo_id, repo_type=repo_type, private=private, exist_ok=True)
    except Exception as exc:
        raise PipelineError(f"Hugging Face repo hazırlanamadı: {exc}") from exc


def upload_huggingface(
    output_root: Path, repo_id: str, *, repo_type: str = "dataset", token: str | None = None,
    private: bool = False, message: str, max_ops_per_commit: int = DEFAULT_MAX_OPS_PER_COMMIT,
    dry_run: bool = False,
) -> list[str]:
    uploads = collect_uploads(output_root)
    if not uploads:
        raise PipelineError("Yüklenecek dosya yok.")
    if dry_run:
        emit_json({"repo": repo_id, "files": len(uploads), "commits": (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit})
        return []
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError as exc:
        raise PipelineError("Hugging Face bağımlılıkları kurulu değil.") from exc
    resolved_token = token or os.getenv("HF_TOKEN")
    if not resolved_token:
        raise PipelineError("Hugging Face write token gerekli.")
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    api = HfApi(token=resolved_token)
    ensure_huggingface_repo(api, repo_id, repo_type, private)
    urls: list[str] = []
    total = (len(uploads) + max_ops_per_commit - 1) // max_ops_per_commit
    for start in range(0, len(uploads), max_ops_per_commit):
        chunk = uploads[start:start + max_ops_per_commit]
        operations = [CommitOperationAdd(path_in_repo=remote, path_or_fileobj=str(local)) for local, remote in chunk]
        part = start // max_ops_per_commit + 1
        suffix = "" if total == 1 else f" ({part}/{total})"
        try:
            result = api.create_commit(repo_id=repo_id, repo_type=repo_type, operations=operations, commit_message=message + suffix)
        except Exception as exc:
            raise PipelineError(f"Hugging Face yüklemesi başarısız ({part}/{total}): {exc}") from exc
        urls.append(str(result.commit_url))
    return urls


def update_asset_files(output_root: Path, manifests: Sequence[dict[str, Any]], storage: dict[str, Any]) -> None:
    for manifest in manifests:
        manifest["storage"] = storage
        manifest["hfPath"] = f"objects/{manifest['assetId'][:2]}/{manifest['assetId']}"
        asset_dir = output_root / "objects" / manifest["assetId"][:2] / manifest["assetId"]
        (asset_dir / "asset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def github_request(url: str, token: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "OdiumFlix",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise PipelineError(f"GitHub katalog isteği başarısız: HTTP {exc.code} {detail[:1500]}") from exc


def _identity(value: dict[str, Any]) -> tuple[Any, ...]:
    external = value.get("externalIds") or {}
    if external.get("imdb"):
        return ("imdb", str(external["imdb"]).lower())
    if external.get("tmdb"):
        return ("tmdb", str(external["tmdb"]), value.get("contentType") or "movie")
    episode = value.get("episode") or {}
    return (
        "title", str(value.get("title") or "").strip().casefold(),
        value.get("contentType") or "movie", episode.get("season"), episode.get("number"),
    )


def _catalog_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    asset_id = manifest["assetId"]
    return {
        "schemaVersion": manifest.get("schemaVersion", 4),
        "assetId": asset_id,
        "title": manifest["title"],
        "userTitle": manifest.get("userTitle"),
        "contentType": manifest["contentType"],
        "durationSeconds": manifest.get("durationSeconds"),
        "metadata": manifest.get("metadata"),
        "artwork": manifest.get("artwork"),
        "trailerUrl": manifest.get("trailerUrl"),
        "externalIds": manifest.get("externalIds"),
        "episode": manifest.get("episode"),
        "source": manifest.get("source"),
        "playback": manifest.get("playback") or {"mode": "unavailable", "master": None, "directFile": None, "qualities": [], "audio": [], "subtitles": []},
        "storage": manifest.get("storage"),
        "hfPath": manifest.get("hfPath") or f"objects/{asset_id[:2]}/{asset_id}",
        "warnings": manifest.get("warnings") or [],
        "createdAt": manifest.get("createdAt"),
        "updatedAt": int(time.time()),
    }


def update_github_catalog(
    manifests: Sequence[dict[str, Any]], *, repository: str, token: str,
    branch: str = "main", path: str = "catalog/media/index.json",
) -> str:
    encoded_path = urllib.parse.quote(path)
    api_url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
    sha = None
    current: dict[str, Any] = {"schemaVersion": 4, "assets": {}}
    try:
        payload = github_request(api_url + "?ref=" + urllib.parse.quote(branch), token)
        sha = payload.get("sha")
        current = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    except PipelineError as exc:
        if "HTTP 404" not in str(exc):
            raise
    current["schemaVersion"] = 4
    assets = current.setdefault("assets", {})
    for manifest in manifests:
        asset_id = manifest["assetId"]
        incoming_identity = _identity(manifest)
        for existing_id, existing in list(assets.items()):
            if existing_id != asset_id and isinstance(existing, dict) and _identity(existing) == incoming_identity:
                del assets[existing_id]
        assets[asset_id] = _catalog_entry(manifest)
    content = base64.b64encode(json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    body: dict[str, Any] = {"message": f"Catalog batch: {len(manifests)} media asset(s)", "content": content, "branch": branch}
    if sha:
        body["sha"] = sha
    payload = github_request(api_url, token, method="PUT", data=body)
    return payload["commit"]["html_url"]
