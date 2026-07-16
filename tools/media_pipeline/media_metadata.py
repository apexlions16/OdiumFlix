from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from media_common import PipelineError


def sanitize_tmdb_credential(value: str) -> str:
    credential = value.strip().strip('"').strip("'")
    if credential.lower().startswith("bearer "):
        credential = credential[7:].strip()
    return credential


def tmdb_request(path: str, credential: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = sanitize_tmdb_credential(credential)
    if not token:
        raise PipelineError("TMDB anahtarı boş.")
    query = dict(params or {})
    headers = {"accept": "application/json", "User-Agent": "OdiumFlix/0.3.0-alpha.2"}
    if re.fullmatch(r"[A-Fa-f0-9]{32}", token):
        query["api_key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.themoviedb.org/3/{path.lstrip('/')}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if exc.code == 401:
            raise PipelineError(
                "TMDB kimlik bilgisi geçersiz (401). TMDB API ayarlarından ya API Read Access Token "
                "(genellikle eyJ… ile başlar) ya da 32 karakterli v3 API Key gir. 'Bearer ' yazısını ekleme."
            ) from exc
        raise PipelineError(f"TMDB isteği başarısız: HTTP {exc.code} {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"TMDB bağlantısı kurulamadı: {exc.reason}") from exc


def choose_trailer(videos: Iterable[dict[str, Any]]) -> str | None:
    values = [v for v in videos if v.get("site") == "YouTube" and v.get("key")]
    values.sort(key=lambda v: (
        v.get("official") is True,
        v.get("type") == "Trailer",
        v.get("type") == "Teaser",
        v.get("published_at") or "",
    ), reverse=True)
    return f"https://www.youtube.com/watch?v={values[0]['key']}" if values else None


def fetch_metadata(*, title: str | None, imdb_id: str | None, token: str, language: str = "tr-TR") -> dict[str, Any]:
    if imdb_id:
        found = tmdb_request(f"find/{imdb_id}", token, {"external_source": "imdb_id", "language": language})
        movie_results = found.get("movie_results") or []
        tv_results = found.get("tv_results") or []
        candidate = (movie_results or tv_results or [None])[0]
        if not candidate:
            raise PipelineError(f"IMDb kimliği için TMDB kaydı bulunamadı: {imdb_id}")
        media_type = "movie" if movie_results else "tv"
        media_id = candidate["id"]
    elif title:
        found = tmdb_request("search/multi", token, {"query": title, "language": language, "include_adult": "false"})
        candidates = [r for r in found.get("results", []) if r.get("media_type") in {"movie", "tv"}]
        if not candidates:
            raise PipelineError(f"Metadata bulunamadı: {title}")
        candidate = candidates[0]
        media_type, media_id = candidate["media_type"], candidate["id"]
    else:
        raise PipelineError("Metadata için başlık veya IMDb kimliği gerekli.")

    details = tmdb_request(
        f"{media_type}/{media_id}", token,
        {"language": language, "append_to_response": "images,external_ids,credits,videos,content_ratings,release_dates"},
    )
    cast = [
        {"name": p.get("name"), "character": p.get("character"), "profilePath": p.get("profile_path")}
        for p in (details.get("credits") or {}).get("cast", [])[:40]
    ]
    crew = [
        {"name": p.get("name"), "job": p.get("job"), "department": p.get("department")}
        for p in (details.get("credits") or {}).get("crew", [])[:60]
    ]
    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")
    return {
        "provider": "tmdb", "tmdbId": media_id,
        "imdbId": (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id") or imdb_id,
        "type": media_type, "title": details.get("title") or details.get("name"),
        "originalTitle": details.get("original_title") or details.get("original_name"),
        "overview": details.get("overview"),
        "releaseDate": details.get("release_date") or details.get("first_air_date"),
        "runtime": details.get("runtime") or ((details.get("episode_run_time") or [None])[0]),
        "genres": [g["name"] for g in details.get("genres", [])],
        "posterPath": poster_path, "backdropPath": backdrop_path,
        "posterUrl": f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else None,
        "backdropUrl": f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None,
        "cast": cast, "crew": crew,
        "trailerUrl": choose_trailer((details.get("videos") or {}).get("results", [])),
    }
