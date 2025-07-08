import os
import uuid
import json
import time
import subprocess
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import UploadFile, File, Body
from typing import Optional
import shutil
import requests

BASE_DIR = os.path.dirname(__file__)
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
MEDIA_DIR = os.path.join(BASE_DIR, 'media')
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*']
)

# ---------- helpers ----------

def run(cmd: list[str]) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode, res.stdout.decode(), res.stderr.decode()

def audio_codec(path: str) -> str | None:
    rc, out, _ = run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'stream=codec_name',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        path
    ])
    if rc:
        return None
    return out.strip()

def process(src: str):
    """Convert or move uploaded video to MEDIA_DIR structure and extract subtitles."""
    ext = os.path.splitext(src)[1].lower()
    if ext not in {'.mkv', '.mp4'}:
        return

    name = os.path.splitext(os.path.basename(src))[0]
    dest_dir = os.path.join(MEDIA_DIR, name)
    os.makedirs(dest_dir, exist_ok=True)

    dst_mp4 = os.path.join(dest_dir, f"{name}.mp4")

    # If file is already an MP4 and can be copied directly
    if ext == '.mp4':
        cmd = ['ffmpeg', '-y', '-i', src, '-c', 'copy', '-movflags', '+faststart', dst_mp4]
    else:  # .mkv → .mp4 (rewrap / transcode if needed)
        acodec = audio_codec(src)
        if acodec == 'aac':
            cmd = ['ffmpeg', '-y', '-i', src, '-c', 'copy', '-movflags', '+faststart', dst_mp4]
        else:
            cmd = [
                'ffmpeg', '-y', '-i', src,
                '-c:v', 'copy',
                '-c:a', 'aac', '-ac', '2', '-b:a', '128k', '-ar', '44100',
                '-movflags', '+faststart', dst_mp4
            ]

    rc, _, err = run(cmd)
    if rc:
        print(f"Error processing {src}: {err}")
        return

    print(f"Successfully prepared {dst_mp4}")

    # Attempt subtitle extraction (first subtitle stream → WebVTT)
    rc2, meta_json, _ = run([
        'ffprobe', '-v', 'error',
        '-select_streams', 's',
        '-show_entries', 'stream=index,codec_name',
        '-of', 'json', src
    ])

    try:
        subs_info = json.loads(meta_json)
    except Exception:
        subs_info = {}

    streams = subs_info.get('streams', [])
    if streams:
        vtt_path = os.path.join(dest_dir, f"{name}.vtt")
        rc3, _, err3 = run([
            'ffmpeg', '-y', '-i', src,
            '-map', '0:s:0',
            '-c:s', 'webvtt', vtt_path
        ])
        if rc3:
            print(f"Failed to extract subtitles from {src}: {err3}")
        else:
            print(f"Subtitles extracted → {vtt_path}")

    # Cleanup original upload
    os.remove(src)

# ---------- file watcher ----------

class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        _, ext = os.path.splitext(event.src_path)
        if ext.lower() in {'.mkv', '.mp4'}:
            print(f"New video detected: {event.src_path}")
            # Give the file a moment to finish writing completely
            time.sleep(1)
            process(event.src_path)

def start_watcher():
    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, UPLOADS_DIR, recursive=False)
    observer.start()
    print(f"Watching directory: {UPLOADS_DIR}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# Run the watcher in a separate thread
watcher_thread = threading.Thread(target=start_watcher, daemon=True)
watcher_thread.start()

# ---------- api ----------

@app.get('/video')
def stream_latest(range_header: str | None = Header(None, alias='Range')):
    title = latest_title()
    if title is None:
        raise HTTPException(404, 'No MP4 video found')

    return stream_video(title, range_header)

@app.get('/video/{title}')
def stream_video(title: str, range_header: str | None = Header(None, alias='Range')):
    path = mp4_path(title)
    if not os.path.exists(path):
        raise HTTPException(404, 'Video not found')

    size = os.path.getsize(path)

    if range_header is None:
        # --- Full file (200) ---
        def file_iter():
            with open(path, 'rb') as f:
                yield from f
        headers = {
            'Content-Length': str(size),
            'Accept-Ranges': 'bytes'
        }
        return StreamingResponse(file_iter(), media_type='video/mp4', headers=headers)

    # --- Partial (206) ---
    range_header = range_header.replace('bytes=', '')
    start_str, end_str = range_header.split('-')
    start = int(start_str)
    end = int(end_str) if end_str else size - 1

    # Sanity bounds
    end = min(end, size - 1)
    chunk = end - start + 1

    def chunk_iter():
        with open(path, 'rb') as f:
            f.seek(start)
            remaining = chunk
            while remaining:
                data = f.read(min(1024*1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        'Content-Range': f'bytes {start}-{end}/{size}',
        'Accept-Ranges': 'bytes',
        'Content-Length': str(chunk)
    }
    return StreamingResponse(chunk_iter(), status_code=206, media_type='video/mp4', headers=headers)

@app.get('/current')
def current():
    title = latest_title()
    if title is None:
        raise HTTPException(404, 'No media present')

    mp4_exists = os.path.exists(mp4_path(title))
    if mp4_exists:
        sub_exists = os.path.exists(vtt_path(title))
        return {"processing": False, "name": f"{title}.mp4", "title": title, "subtitle": sub_exists}
    else:
        return {"processing": True, "name": title}

@app.get('/subtitle')
def subtitle_latest():
    title = latest_title()
    if title is None:
        raise HTTPException(404, 'No subtitles')
    return subtitle_title(title)

@app.get('/subtitle/{title}')
def subtitle_title(title: str):
    vpath = vtt_path(title)
    if not os.path.exists(vpath):
        raise HTTPException(404, 'No subtitles')

    def sub_iter():
        with open(vpath, 'rb') as f:
            yield from f
    size = os.path.getsize(vpath)
    return StreamingResponse(sub_iter(), media_type='text/vtt', headers={
        'Content-Length': str(size),
        'Access-Control-Allow-Origin': '*'
    })

# ---------- media helpers ----------

def list_media_dirs() -> list[str]:
    """Return all media subdirectories sorted by most recently modified (newest first)."""
    dirs = [d for d in os.listdir(MEDIA_DIR) if os.path.isdir(os.path.join(MEDIA_DIR, d))]
    dirs.sort(key=lambda d: os.path.getmtime(os.path.join(MEDIA_DIR, d)), reverse=True)
    return dirs

def mp4_path(title: str) -> str:
    return os.path.join(MEDIA_DIR, title, f"{title}.mp4")

def vtt_path(title: str) -> str:
    return os.path.join(MEDIA_DIR, title, f"{title}.vtt")

def latest_title() -> Optional[str]:
    dirs = list_media_dirs()
    return dirs[0] if dirs else None

# List all processed media directories (newest first)
@app.get('/media')
def list_media():
    return {"files": list_media_dirs()}

# ---------- upload api ----------

def _unique_dest(name: str) -> str:
    """Return a unique path in UPLOADS_DIR avoiding collisions."""
    base, ext = os.path.splitext(name)
    candidate = os.path.join(UPLOADS_DIR, name)
    while os.path.exists(candidate):
        candidate = os.path.join(UPLOADS_DIR, f"{base}_{uuid.uuid4().hex[:6]}{ext}")
    return candidate

@app.post('/upload')
async def upload_endpoint(
    file: UploadFile | None = File(None),
    url: str | None = Body(None),
):
    """Upload a video via multipart file or remote URL.

    • Multipart: `curl -F "file=@/path/video.mkv" http://server/upload`
    • Remote URL: `curl -H "Content-Type: application/json" -d '{"url":"https://.../video.mp4"}' http://server/upload`
    """

    if file is None and url is None:
        raise HTTPException(400, 'Provide either file or url')

    if file is not None and url is not None:
        raise HTTPException(400, 'Provide only one of file or url')

    if file is not None:
        dest = _unique_dest(file.filename)
        with open(dest, 'wb') as out:
            # Use shutil to copy file efficiently
            shutil.copyfileobj(file.file, out)
        return {'status': 'ok', 'saved': os.path.basename(dest)}

    # --- url path ---
    try:
        resp = requests.get(url, stream=True, timeout=30)
    except Exception as e:
        raise HTTPException(400, f'Error fetching url: {e}')

    if resp.status_code != 200:
        raise HTTPException(400, f'Failed to download – status {resp.status_code}')

    # Determine filename
    filename = url.split('/')[-1].split('?')[0] or f'{uuid.uuid4().hex}.video'
    dest = _unique_dest(filename)

    try:
        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        if os.path.exists(dest):
            os.remove(dest)
        raise HTTPException(500, f'Failed to save file: {e}')

    return {'status': 'ok', 'saved': os.path.basename(dest)}

