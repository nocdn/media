import React, { useEffect, useState, useRef } from "react";
import { CirclePlay, Check, X } from "lucide-react";
import Spinner from "./spinner";
import { AnimatePresence, motion } from "motion/react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [mediaList, setMediaList] = useState([]);
  const [mediaListLoading, setMediaListLoading] = useState(false);
  // keep track of the last played title between visits
  const [currentTitle, setCurrentTitle] = useState(() => {
    // read from localStorage lazily so we only touch it once on mount
    if (typeof window === "undefined") return null;
    return localStorage.getItem("last-watched") || null;
  });
  const [hasSubtitle, setHasSubtitle] = useState(false);

  const pollRef = useRef(null);
  const videoRef = useRef(null);
  const lastUpdateTime = useRef(0);
  const [showingRestored, setShowingRestored] = useState(false);

  // ---------- progress tracking ----------

  const saveProgress = () => {
    if (!videoRef.current || !currentTitle) return;
    const { currentTime } = videoRef.current;
    if (currentTime > 0) {
      localStorage.setItem(
        `video-progress-${currentTitle}`,
        String(currentTime)
      );
    }
  };

  const handleTimeUpdate = () => {
    const now = Date.now();
    if (now - lastUpdateTime.current < 3000) return;
    saveProgress();
    lastUpdateTime.current = now;
  };

  const restoreProgress = () => {
    if (!videoRef.current || !currentTitle) return;
    const savedTime = localStorage.getItem(`video-progress-${currentTitle}`);
    if (savedTime) {
      videoRef.current.currentTime = parseFloat(savedTime);
      setShowingRestored(true);
      setTimeout(() => {
        setShowingRestored(false);
      }, 2000);
      console.log(
        `restoring progress for ${currentTitle} to ${parseFloat(
          savedTime
        ).toFixed(2)}s`
      );
    }
  };

  // ---------- helpers ----------

  const pollCurrent = async () => {
    try {
      const res = await fetch("/api/current");
      if (!res.ok) return;
      const data = await res.json();
      if (data.processing) {
        setProcessing(true);
        return;
      }
      setProcessing(false);
      setInfo(data);

      // do not override an explicitly watched title stored in localStorage
      const saved = localStorage.getItem("last-watched");
      if (!saved) {
        const newTitle = data.title ?? data.name.replace(/\.mp4$/, "");
        setCurrentTitle(newTitle);
        // stash for next visit so we remember what was auto-played
        localStorage.setItem("last-watched", newTitle);
      }

      setHasSubtitle(!!data.subtitle);
    } catch (_) {}
  };

  const fetchMedia = async () => {
    setMediaListLoading(true);
    try {
      const res = await fetch("/api/media");
      if (res.ok) {
        const data = await res.json();
        setMediaList(data.files || []);
      }
    } catch (_) {}
    setMediaListLoading(false);
  };

  // ---------- effects ----------

  // start / stop polling
  useEffect(() => {
    pollCurrent();
    pollRef.current = setInterval(pollCurrent, 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    fetchMedia();
  }, []);

  // whenever title changes → reload video element
  useEffect(() => {
    if (videoRef.current) {
      console.debug("🔁 switching to", currentTitle ?? "latest");
      videoRef.current.load();
    }
  }, [currentTitle]);

  // save progress on tab close
  useEffect(() => {
    window.addEventListener("beforeunload", saveProgress);
    return () => window.removeEventListener("beforeunload", saveProgress);
  }, [currentTitle]);

  // whenever "currentTitle" changes, (re)check if subtitles are available
  useEffect(() => {
    const checkSubtitle = async () => {
      if (!currentTitle) return;
      try {
        const res = await fetch(`/api/subtitle/${currentTitle}`, {
          method: "HEAD",
        });
        setHasSubtitle(res.ok);
      } catch {
        setHasSubtitle(false);
      }
    };
    checkSubtitle();
  }, [currentTitle]);

  // if the remembered title is no longer in the media list, fall back to latest
  useEffect(() => {
    if (
      currentTitle &&
      mediaList.length > 0 &&
      !mediaList.includes(currentTitle)
    ) {
      setCurrentTitle(null);
      localStorage.removeItem("last-watched");
    }
  }, [mediaList]);

  // ---------- ui handlers ----------

  const selectVideo = async (title) => {
    clearInterval(pollRef.current);
    saveProgress();
    setProcessing(false);
    setCurrentTitle(title);
    // remember choice for next visit
    localStorage.setItem("last-watched", title);
    try {
      const res = await fetch(`/api/subtitle/${title}`, { method: "HEAD" });
      setHasSubtitle(res.ok);
    } catch {
      setHasSubtitle(false);
    }
  };

  // remove a processed video completely
  const deleteVideo = async (title) => {
    try {
      const res = await fetch(`/api/media/${title}`, { method: "DELETE" });
      if (!res.ok) throw new Error("delete failed");

      // update lists locally
      setMediaList((prev) => prev.filter((t) => t !== title));

      // if we were playing this one, reset to latest (null triggers pollCurrent)
      if (currentTitle === title) {
        setCurrentTitle(null);
        localStorage.removeItem("last-watched");
        pollCurrent();
      }
    } catch (e) {
      console.error(e);
      console.log("Delete failed – check backend logs");
    }
  };

  // ---------- paths ----------

  const videoSrc = currentTitle ? `/api/video/${currentTitle}` : `/api/video`;
  const hlsSrc = currentTitle
    ? `/hls/${currentTitle}/index.m3u8`
    : `/hls/latest/index.m3u8`;
  const subtitleSrc = currentTitle
    ? `/api/subtitle/${currentTitle}`
    : `/api/subtitle`;

  // ---------- render ----------

  const [showingNowPlaying, setShowingNowPlaying] = useState(false);

  return (
    <div className="py-4 px-7 font-geist">
      <h1 className="mb-0 font-semibold">video stream</h1>

      {processing && (
        <p className="text-sm text-yellow-400 mt-1 mb-3">processing video…</p>
      )}

      <AnimatePresence>
        {!info && !processing && (
          <motion.div
            onAnimationComplete={() => setShowingNowPlaying(true)}
            exit={{ opacity: 0, y: 10, filter: "blur(1px)" }}
            transition={{ duration: 0.1 }}
            className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3"
          >
            loading video...
          </motion.div>
        )}
      </AnimatePresence>

      {info && !processing && showingNowPlaying && (
        <motion.div
          initial={{ opacity: 0, y: -10, filter: "blur(1px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -10, filter: "blur(1px)" }}
          className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center"
        >
          playing:{" "}
          <AnimatePresence mode="wait">
            <motion.span
              key={currentTitle ? currentTitle : info?.name}
              initial={{ opacity: 0, filter: "blur(1px)", y: -3 }}
              animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
              exit={{ opacity: 0, filter: "blur(1px)", y: 3 }}
              transition={{ duration: 0.15, ease: "easeInOut" }}
              className="text-black dark:text-gray-200 ml-1.5"
            >
              {currentTitle ? `${currentTitle}.mp4` : info?.name}
            </motion.span>
          </AnimatePresence>
        </motion.div>
      )}

      {!processing && (
        <div className="flex justify-center">
          <video
            key={currentTitle || "latest"} // force remount when title changes
            ref={videoRef}
            width="700"
            controls
            className="rounded-md"
            crossOrigin="anonymous"
            onLoadedMetadata={restoreProgress}
            onTimeUpdate={handleTimeUpdate}
          >
            {/* hls first (safari/ios) */}
            <source src={hlsSrc} type="application/x-mpegURL" />
            {/* mp4 fallback */}
            <source src={videoSrc} type="video/mp4" />
            {hasSubtitle && (
              <track
                label="Subtitles"
                kind="subtitles"
                srcLang="en"
                src={subtitleSrc}
                default
              />
            )}
          </video>

          <div className="flex flex-col ml-2 font-geist font-medium">
            <p className="font-jetbrains-mono text-gray-600 font-semibold text-[15px] pl-1.5 mb-1.5 flex items-center gap-2">
              <span>AVAILABLE MEDIA</span>
              {mediaListLoading && <Spinner />}
              {!mediaListLoading && mediaList.length > 0 && (
                <span className="text-gray-400">(click any to play)</span>
              )}
            </p>
            {mediaList.map((name) => (
              <div
                key={name}
                className="px-2 py-1 cursor-pointer flex items-center gap-2 group"
                onClick={() => selectVideo(name)}
              >
                <CirclePlay
                  className="w-4 h-4 group-hover:opacity-100 opacity-60 transition-opacity"
                  strokeWidth={2.25}
                />
                {name}
                <X
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteVideo(name);
                  }}
                  className="h-4 w-4 text-red-700 hover:text-red-500 transition-all hover:scale-120 opacity-0 group-hover:opacity-100 cursor-pointer"
                />
              </div>
            ))}
          </div>
        </div>
      )}
      <AnimatePresence>
        {showingRestored && (
          <motion.div
            className="w-fit font-jetbrains-mono text-green-700 font-semibold text-sm pl-1.5 mt-2.5 flex items-center gap-2"
            initial={{ scale: 0, opacity: 0, y: -20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0, opacity: 0, y: -20 }}
          >
            <Check className="w-4 h-4" />
            <p>progress restored</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
