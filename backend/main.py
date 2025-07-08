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

BASE_DIR = os.path.dirname(__file__)
ACTIVE_DIR = os.path.join(BASE_DIR, 'active')
os.makedirs(ACTIVE_DIR, exist_ok=True)

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
    if not src.endswith('.mkv'):
        return

    dst = os.path.splitext(src)[0] + '.mp4'

    acodec = audio_codec(src)

    if acodec == 'aac':
        # direct re-wrap
        cmd = ['ffmpeg', '-y', '-i', src,
               '-c', 'copy', '-movflags', '+faststart', dst]
    else:
        # copy video, transcode audio to AAC for browser compatibility
        cmd = ['ffmpeg', '-y', '-i', src,
               '-c:v', 'copy',
               '-c:a', 'aac', '-ac', '2', '-b:a', '128k', '-ar', '44100',
               '-movflags', '+faststart', dst]

    rc, _, err = run(cmd)
    if rc:
        print(f'Error processing {src}: {err}')
    else:
        print(f'Successfully processed {src} to {dst} (audio codec: {acodec})')

        # try to extract first subtitle stream to WebVTT for browser
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
            vtt_path = os.path.splitext(dst)[0] + '.vtt'
            rc3, _, err3 = run([
                'ffmpeg', '-y', '-i', src,
                '-map', '0:s:0',
                '-c:s', 'webvtt', vtt_path
            ])
            if rc3:
                print(f'Failed to extract subtitles: {err3}')
            else:
                print(f'Subtitles extracted → {vtt_path}')

        os.remove(src)

# ---------- file watcher ----------

class MKVHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.mkv'):
            print(f"New MKV file detected: {event.src_path}")
            # Give the file a moment to finish writing
            time.sleep(1) 
            process(event.src_path)

def start_watcher():
    event_handler = MKVHandler()
    observer = Observer()
    observer.schedule(event_handler, ACTIVE_DIR, recursive=False)
    observer.start()
    print(f"Watching directory: {ACTIVE_DIR}")
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
def stream(range_header: str | None = Header(None, alias='Range')):
    mp4_files = [f for f in os.listdir(ACTIVE_DIR) if f.endswith('.mp4')]
    if not mp4_files:
        raise HTTPException(404, 'No MP4 video found')

    path = os.path.join(ACTIVE_DIR, mp4_files[0])
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
    mp4_files = [f for f in os.listdir(ACTIVE_DIR) if f.endswith('.mp4')]
    mkv_files = [f for f in os.listdir(ACTIVE_DIR) if f.endswith('.mkv')]

    if mp4_files:
        # video ready
        name = mp4_files[0]
        sub_exists = os.path.exists(
            os.path.join(ACTIVE_DIR, os.path.splitext(name)[0] + '.vtt')
        )
        return {
            'processing': False,
            'name': name,
            'subtitle': sub_exists,
        }

    # no mp4 yet
    if mkv_files:
        return {
            'processing': True,
            'mkv': mkv_files[0]
        }

    # nothing uploaded
    raise HTTPException(404, 'No video present')

@app.get('/subtitle')
def subtitle():
    mp4_files = [f for f in os.listdir(ACTIVE_DIR) if f.endswith('.mp4')]
    if not mp4_files:
        raise HTTPException(404, 'No MP4 video found')
    vtt_path = os.path.join(ACTIVE_DIR, os.path.splitext(mp4_files[0])[0] + '.vtt')
    if not os.path.exists(vtt_path):
        raise HTTPException(404, 'No subtitles')

    def sub_iter():
        with open(vtt_path, 'rb') as f:
            yield from f
    size = os.path.getsize(vtt_path)
    return StreamingResponse(sub_iter(), media_type='text/vtt', headers={
        'Content-Length': str(size),
        'Access-Control-Allow-Origin': '*'
    })

