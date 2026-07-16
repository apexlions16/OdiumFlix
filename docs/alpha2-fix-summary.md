# Alpha.2 fix summary

- Video quality selections are catalog labels only.
- Video streams are never resized or re-encoded.
- Supplied variants are packaged with stream copy.
- Packaged Windows Studio resolves FFmpeg/ffprobe from `resources/media-tools`, outside `app.asar`.
- TMDB accepts Read Access Tokens and v3 API keys; metadata failures are warnings and do not block media upload.
- Windows console output is forced to UTF-8-safe handling.
- CI checks source/output video packet hashes and executes the packaged ffprobe binary.
