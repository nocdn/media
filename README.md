# Media

> a simple media server that converts videos to mp4 and serves them in a web-client.

This project consists of:

- **backend/** – FastAPI service that watches an `uploads/` directory, converts videos (MKV → MP4), extracts subtitles, and serves/streams media.
- **frontend/** – React + Vite web-client that auto-plays the newest video and lets you pick others.
- **media/** – directory that contains the converted media.

---

## Running locally

```bash
# 1. install backend deps (Python 3.11+)
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. start backend (http://localhost:8000)
uvicorn main:app --reload

# 3. start frontend in another shell
cd ../frontend
bun install
bun run dev   # http://localhost:5173 by default
```

---

## API Endpoints

> Base URL examples assume the backend is running on `http://localhost:8000`.

### 1. `POST /upload`

Upload or remotely fetch a video into `backend/uploads/`.

_Multipart file upload_

```bash
curl -F "file=@/path/to/video.mkv" \
     http://localhost:8000/upload
```

_Remote URL fetch_

```bash
curl -H "Content-Type: application/json" \
     -d '{"url":"https://example.com/myvideo.mp4"}' \
     http://localhost:8000/upload
```

Response

```json
{ "status": "ok", "saved": "myvideo.mp4" }
```

### 2. `GET /media`

Return a JSON list of processed media folders (newest → oldest).

```bash
curl http://localhost:8000/media
# → { "files": ["myvideo", "starwars", ...] }
```

### 3. `GET /video`

Stream the newest MP4 (HTTP range requests supported).

```bash
curl -O http://localhost:8000/video
```

### 4. `GET /video/{title}`

Stream a specific video (without ".mp4" extension).

```bash
curl -O http://localhost:8000/video/starwars
```

### 5. `GET /subtitle`

Subtitles for the newest video (WebVTT).

### 6. `GET /subtitle/{title}`

Subtitles for a specific title.

A quick HEAD request is useful to check if subtitles exist:

```bash
curl -I http://localhost:8000/subtitle/starwars
```

### 7. `GET /current`

Returns processing status for the newest upload.

```bash
curl http://localhost:8000/current
# { "processing": false, "name": "starwars.mp4", "title": "starwars", "subtitle": true }
```

### 8. `DELETE /media/{title}`

Remove an entire processed media folder.

```bash
curl -X DELETE http://localhost:8000/media/starwars
# { "status": "deleted", "title": "starwars" }
```

---

## File-system overview

```
backend/
  uploads/    # incoming files (watched)
  media/
    ├── starwars/
    │   ├── starwars.mp4
    │   └── starwars.vtt
    └── another-video/
        └── another-video.mp4
```

- Drop or upload any `.mkv` / `.mp4` into `uploads/` (or use `/upload`).
- The watcher converts & moves output into `media/<title>/` and cleans up the upload.
