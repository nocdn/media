# Media

> a tiny self-hosted media server – drop an `.mkv`/`.mp4` into **uploads/** and get an MP4 + HLS streamable in any browser (Safari included) through a minimalist web-client.

This repository now contains:

- **backend/** – FastAPI service that
  - watches the `uploads/` folder
  - converts/rewraps videos (MKV → MP4, AAC audio if needed)
  - generates an **HLS (fMP4) playlist** for Safari/iOS (no re-encode)
  - extracts subtitles (→ WebVTT)
  - streams MP4 or HLS + subs on demand.
- **frontend/** – React + Vite client that auto-plays the newest video and lets you pick others (it tries HLS first, MP4 fallback for every other browser).
- **backend/media/** – ready-to-serve output (`<title>.mp4`, `hls/index.m3u8`, `<title>.vtt` …).

---

## Running locally

```bash
# 1. install backend deps (Python 3.11+)
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. start backend  →  http://localhost:9420
uvicorn main:app --reload --port 9420

# 3. in another shell run the frontend
cd ../frontend
bun install
bun run dev           # http://localhost:9410
```

---

## API Endpoints (backend)

_Base URLs below assume the backend is reachable at `http://localhost:9420`._

### `POST /upload`

Put a new file into `backend/uploads/` (the watcher converts it automatically).

a) multipart **file** upload

```bash
curl -F "file=@/path/to/video.mkv" \
     http://localhost:9420/upload
```

b) multipart **URL** field (no local file)

```bash
curl -F "url=https://example.com/myvideo.mp4" \
     http://localhost:9420/upload
```

c) raw JSON **string** (easiest for scripts)

```bash
curl http://localhost:9420/upload \
     -H 'Content-Type: application/json' \
     --data '"https://example.com/myvideo.mp4"'
```

d) tiny JSON **object** (old style, still works)

```bash
curl http://localhost:9420/upload \
     -H 'Content-Type: application/json' \
     --data '{"url":"https://example.com/myvideo.mp4"}'
```

All four return

```json
{ "status": "ok", "saved": "myvideo.mp4" }
```

### `GET /media`

List processed media directories (newest → oldest).

```bash
curl http://localhost:9420/media
# → { "files": ["myvideo", "wicked", ...] }
```

### `GET /video` or `GET /video/{title}`

Progressive-download MP4 stream (range requests supported).

### `GET /hls/latest/index.m3u8` or `GET /hls/{title}/index.m3u8`

HLS playlist for Safari / iOS (segments are under the same `/hls/<title>/…` path).

### `GET /subtitle` or `GET /subtitle/{title}`

WebVTT subtitles (if extracted).

### `GET /current`

JSON status for the newest upload.

### `DELETE /media/{title}`

Remove an entire processed folder.

---

## File-system layout

```
backend/
  uploads/          # incoming (watched)
  media/
    wicked/
      wicked.mp4
      hls/
        index.m3u8
        index0.m4s
        …
      wicked.vtt
    another-video/
      another-video.mp4
      hls/
      …
```

1. Drop/POST any `.mkv`/`.mp4` into **uploads/** (or call `/upload`).
2. The watcher waits for the file to finish **writing/closing**, then:
   - prepares `<title>.mp4` (copy video, AAC audio if needed, fast-start)
   - slices it into **fMP4 HLS** (`hls/index.m3u8`, `index*.m4s`)
   - extracts the first subtitle stream (`.vtt`) if present
   - deletes the original upload.

---

## Running with Docker

A ready-made **docker-compose.yml** builds and runs both services.

```bash
docker compose up -d --build

# open:
# → frontend  http://localhost:9410
# → backend   http://localhost:9420
```

### Compose details

| service  | image                              | port | notes                                                                       |
| -------- | ---------------------------------- | ---- | --------------------------------------------------------------------------- |
| backend  | custom (Python 3.12-slim + ffmpeg) | 9420 | bind-mounts `backend/uploads` & `backend/media` so videos survive restarts  |
| frontend | multi-stage Bun → Nginx            | 9410 | Nginx proxies `/api/*` & `/hls/*` to the backend for a single-origin client |

Check logs with:

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Browser support

- Safari / iOS → gets HLS automatically.
- Chrome / Firefox / Edge → fall back to MP4 progressive.

No re-encoding is done; generating HLS is a light copy operation, so the server runs happily even on low-powered VPSs.
