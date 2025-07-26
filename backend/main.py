import os
import uuid
import json
import time
import subprocess
import threading
import logging
import queue
from typing import Optional
import shutil
import requests
from urllib.parse import unquote

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Body, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------- logging setup ----------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.DEBUG,  # change to INFO in prod
)
log = logging.getLogger(__name__)

# ---------- dirs ----------
BASE_DIR = os.path.dirname(__file__)
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
MEDIA_DIR = os.path.join(BASE_DIR, "media")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# ---------- fastapi ----------
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------- helpers ----------


def run(cmd: list[str]) -> tuple[int, str, str]:
    """run subprocess and capture out/err"""
    log.debug("cmd ▶ %s", " ".join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = res.stdout.decode(), res.stderr.decode()
    if res.returncode:
        log.warning("cmd ❌ rc=%s stderr=%s", res.returncode, err.strip())
    return res.returncode, out, err


def audio_codec(path: str) -> str | None:
    rc, out, _ = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
    )
    return None if rc else out.strip()


def generate_hls(mp4_src: str, dest_dir: str):
    """split mp4 into fmp4 hls playlist w/out re-encoding"""
    hls_dir = os.path.join(dest_dir, "hls")
    os.makedirs(hls_dir, exist_ok=True)
    hls_path = os.path.join(hls_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        mp4_src,
        "-c",
        "copy",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_segment_type",
        "fmp4",
        "-hls_flags",
        "+independent_segments",
        "-hls_playlist_type",
        "vod",
        hls_path,
    ]
    rc, _, _ = run(cmd)
    if rc:
        log.error("hls build failed for %s", mp4_src)
    else:
        log.info("hls ready → %s", hls_path)


def process(src: str):
    """convert/upload → mp4, build hls, extract subs"""
    ext = os.path.splitext(src)[1].lower()
    if ext not in {".mkv", ".mp4"}:
        log.info("skip (not video) %s", src)
        return

    name = os.path.splitext(os.path.basename(src))[0]
    dest_dir = os.path.join(MEDIA_DIR, name)
    os.makedirs(dest_dir, exist_ok=True)
    dst_mp4 = os.path.join(dest_dir, f"{name}.mp4")

    # --- audio decision: always make sure final MP4 has AAC for browser support ---
    acodec = audio_codec(src)
    if acodec == "aac":
        # streams already browser-friendly – quick re-wrap/copy
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            dst_mp4,
        ]
    else:
        # copy video, transcode audio → AAC stereo 128 kbps 48 kHz (widest support)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            dst_mp4,
        ]

    rc, _, _ = run(cmd)
    if rc:
        log.error("mp4 prep failed for %s", src)
        return

    log.info("mp4 ready → %s", dst_mp4)

    # hls
    generate_hls(dst_mp4, dest_dir)

    # subtitles
    rc2, meta_json, _ = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name",
            "-of",
            "json",
            src,
        ]
    )
    try:
        has_subs = bool(json.loads(meta_json).get("streams"))
    except Exception:
        has_subs = False

    if has_subs:
        vtt_path = os.path.join(dest_dir, f"{name}.vtt")
        rc3, _, _ = run(["ffmpeg", "-y", "-i", src, "-map", "0:s:0", "-c:s", "webvtt", vtt_path])
        if rc3:
            log.warning("sub extraction failed for %s", src)
        else:
            log.info("subs extracted → %s", vtt_path)

    # cleanup
    os.remove(src)
    log.debug("upload removed %s", src)


# ---------- serial processing queue ----------

# we want to guarantee that only a single ffmpeg invocation runs at any time.
# a simple Queue + worker thread gives us **strict** serial processing while
# still allowing the watchdog to enqueue many files quickly.

_PROCESS_Q: "queue.Queue[str]" = queue.Queue()
_QUEUED: set[str] = set()
_Q_LOCK = threading.Lock()


def _enqueue(path: str):
    """Add a path to the processing queue (deduplicated)."""
    with _Q_LOCK:
        if path in _QUEUED:
            return  # already queued/processing
        _QUEUED.add(path)
        _PROCESS_Q.put(path)
        log.info("queued %s", path)


def _worker():
    """Background worker that processes items strictly one-by-one."""
    while True:
        path = _PROCESS_Q.get()
        try:
            # wait until the file stops growing – this guards against cases
            # where we catch a partially downloaded file (e.g. curl -o ...).
            last_size = -1
            while True:
                try:
                    size = os.path.getsize(path)
                except FileNotFoundError:
                    # may happen if the file got removed before we got to it
                    log.warning("file disappeared before processing: %s", path)
                    break

                if size == last_size:
                    # size stable → assume download finished
                    break
                last_size = size
                time.sleep(2)  # wait a bit and re-check

            # finally run the heavy lifting
            process(path)
        except Exception as e:
            log.exception("processing error for %s: %s", path, e)
        finally:
            with _Q_LOCK:
                _QUEUED.discard(path)
            _PROCESS_Q.task_done()


# start the single-worker thread
threading.Thread(target=_worker, daemon=True).start()


# ---------- file watcher ----------

class VideoHandler(FileSystemEventHandler):
    """wait until the file is completely written before processing"""

    def __init__(self, debounce: float = 2.0):
        super().__init__()
        # how long a file has to stay unchanged before we treat it as "ready"
        self.debounce = debounce
        # path -> Timer mapping so we can reset the timer on each modification
        self._timers: dict[str, threading.Timer] = {}

    def _maybe_process(self, path: str):
        # cancel any outstanding timer for this path (if we got here via Timer)
        self._timers.pop(path, None)
        _, ext = os.path.splitext(path)
        if ext.lower() in {".mkv", ".mp4"}:
            log.info("file ready → %s (queuing)", path)
            _enqueue(path)

    # closed after writing (most reliable)
    def on_closed(self, event):
        if not event.is_directory and event.event_type == "closed":
            self._maybe_process(event.src_path)

    # in case the file is written elsewhere and moved in
    def on_moved(self, event):
        if not event.is_directory:
            self._maybe_process(event.dest_path)

    # --- new: handle create/modify with debouncing ---
    def _schedule(self, path: str):
        """(re)start a timer; when it fires the file is assumed stable"""
        existing = self._timers.pop(path, None)
        if existing:
            existing.cancel()

        timer = threading.Timer(self.debounce, self._maybe_process, args=[path])
        timer.start()
        self._timers[path] = timer

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

# start watcher
def start_watcher():
    obs = Observer()
    obs.schedule(VideoHandler(), UPLOADS_DIR, recursive=False)
    obs.start()
    log.info("watching %s", UPLOADS_DIR)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()

threading.Thread(target=start_watcher, daemon=True).start()


# ---------- util ----------


def list_media_dirs() -> list[str]:
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


def _resolve_title(title: str) -> str:
    return latest_title() if title == "latest" else title


# ---------- hls endpoints ----------


@app.get("/hls/{title}/index.m3u8")
def hls_playlist(title: str):
    real = _resolve_title(title)
    path = os.path.join(MEDIA_DIR, real, "hls", "index.m3u8")
    log.debug("playlist req %s -> %s", title, path)
    if not os.path.exists(path):
        raise HTTPException(404, "playlist not found")
    return FileResponse(path, media_type="application/x-mpegURL")


@app.get("/hls/{title}/{segment:path}")
def hls_segment(title: str, segment: str):
    real = _resolve_title(title)
    path = os.path.join(MEDIA_DIR, real, "hls", segment)
    log.debug("segment req %s/%s", real, segment)
    if not os.path.exists(path):
        raise HTTPException(404, "segment not found")
    return FileResponse(path, media_type="video/iso.segment")


# ---------- video streaming ----------


@app.get("/video")
def stream_latest(range_header: str | None = Header(None, alias="Range")):
    title = latest_title()
    if title is None:
        raise HTTPException(404, "no mp4")
    return stream_video(title, range_header)


@app.get("/video/{title}")
def stream_video(title: str, range_header: str | None = Header(None, alias="Range")):
    path = mp4_path(title)
    if not os.path.exists(path):
        raise HTTPException(404, "video not found")

    size = os.path.getsize(path)
    log.debug("mp4 request %s size=%s", title, size)

    if range_header is None:
        def file_iter():
            with open(path, "rb") as f:
                yield from f

        headers = {"Content-Length": str(size), "Accept-Ranges": "bytes"}
        return StreamingResponse(file_iter(), media_type="video/mp4", headers=headers)

    range_header = range_header.replace("bytes=", "")
    start_str, end_str = range_header.split("-")
    start = int(start_str)
    end = int(end_str) if end_str else size - 1
    end = min(end, size - 1)
    chunk = end - start + 1

    def chunk_iter():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = chunk
            while remaining:
                data = f.read(min(1024 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk),
    }
    return StreamingResponse(chunk_iter(), status_code=206, media_type="video/mp4", headers=headers)


# ---------- current / media ----------


@app.get("/current")
def current():
    title = latest_title()
    if title is None:
        raise HTTPException(404, "no media")

    mp4_exists = os.path.exists(mp4_path(title))
    sub_exists = os.path.exists(vtt_path(title))
    return {
        "processing": not mp4_exists,
        "name": f"{title}.mp4",
        "title": title,
        "subtitle": sub_exists,
    }


@app.get("/media")
def list_media():
    return {"files": list_media_dirs()}


# ---------- subtitles ----------


@app.api_route("/subtitle", methods=["GET", "HEAD"])
def subtitle_latest():
    title = latest_title()
    if title is None:
        raise HTTPException(404, "no subs")
    return subtitle_title(title)


@app.api_route("/subtitle/{title}", methods=["GET", "HEAD"])
def subtitle_title(title: str):
    vpath = vtt_path(title)
    if not os.path.exists(vpath):
        raise HTTPException(404, "no subs")

    def sub_iter():
        with open(vpath, "rb") as f:
            yield from f

    size = os.path.getsize(vpath)
    return StreamingResponse(
        sub_iter(), media_type="text/vtt", headers={"Content-Length": str(size)}
    )


# ---------- upload ----------


def _unique_dest(name: str) -> str:
    base, ext = os.path.splitext(name)
    candidate = os.path.join(UPLOADS_DIR, name)
    while os.path.exists(candidate):
        candidate = os.path.join(UPLOADS_DIR, f"{base}_{uuid.uuid4().hex[:6]}{ext}")
    return candidate


# ---------- upload api ----------

@app.post("/upload")
async def upload_endpoint(
    request: Request,
    file: UploadFile | None = File(None),
):
    """
    accept either:
      • multipart file field    → ?file=<UploadFile>
      • multipart url field     → ?url=<http://...>
      • raw json string         → "http://..."
      • json object             → { "url": "http://..." }
    """

    url: str | None = None

    ct = request.headers.get("content-type", "")
    is_json = ct.startswith("application/json")
    is_multipart = ct.startswith("multipart/")

    # --- pull url from json body ---
    if is_json:
        try:
            data = await request.json()
            if isinstance(data, str):
                url = data
            elif isinstance(data, dict):
                url = data.get("url")
        except Exception as e:
            log.debug("json parse error: %s", e)

    # --- pull url from multipart field ---
    if is_multipart and file is None:  # no file means maybe just a url part
        form = await request.form()
        url = form.get("url")

    if file is None and url is None:
        raise HTTPException(400, "provide either file or url")

    if file is not None and url is not None:
        raise HTTPException(400, "provide only one of file or url")

    # ---------- file path ----------
    if file is not None:
        dest = _unique_dest(file.filename)
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
        log.info("upload saved %s", dest)
        return {"status": "ok", "saved": os.path.basename(dest)}

    # ---------- remote url path ----------
    log.info("downloading remote %s", url)
    try:
        resp = requests.get(url, stream=True, timeout=30)
    except Exception as e:
        raise HTTPException(400, f"fetch error: {e}")

    if resp.status_code != 200:
        raise HTTPException(400, f"status {resp.status_code}")

    # Extract filename and decode URL-encoded characters
    filename = url.split("/")[-1].split("?")[0] or f"{uuid.uuid4().hex}.video"
    filename = unquote(filename)  # Decode %20 to spaces, etc.
    dest = _unique_dest(filename)

    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        if os.path.exists(dest):
            os.remove(dest)
        raise HTTPException(500, f"save fail: {e}")

    log.info("remote saved %s", dest)
    return {"status": "ok", "saved": os.path.basename(dest)}


# ---------- delete ----------


@app.delete("/media/{title}")
def delete_media(title: str):
    dir_path = os.path.join(MEDIA_DIR, title)
    if not os.path.isdir(dir_path):
        raise HTTPException(404, "not found")
    shutil.rmtree(dir_path)
    log.info("deleted %s", dir_path)
    return {"status": "deleted", "title": title}
