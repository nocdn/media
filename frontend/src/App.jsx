import React, { useEffect, useState, useRef } from "react";
import { CirclePlay, Check } from "lucide-react";
import Spinner from "./spinner";
import { AnimatePresence, motion } from "motion/react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [mediaList, setMediaList] = useState([]);
  const [mediaListLoading, setMediaListLoading] = useState(false);
  const [currentTitle, setCurrentTitle] = useState(null);
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
      setCurrentTitle(data.title ?? data.name.replace(/\.mp4$/, ""));
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

  // ---------- ui handlers ----------

  const selectVideo = async (title) => {
    clearInterval(pollRef.current);
    saveProgress();
    setProcessing(false);
    setCurrentTitle(title);
    try {
      const res = await fetch(`/api/subtitle/${title}`, { method: "HEAD" });
      setHasSubtitle(res.ok);
    } catch {
      setHasSubtitle(false);
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

  return (
    <div className="p-4 font-geist">
      <h1 className="mb-0 font-semibold">video stream</h1>

      {processing && (
        <p className="text-sm text-yellow-400 mt-1 mb-3">processing video…</p>
      )}

      {!info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3">
          loading video...
        </p>
      )}

      {info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center">
          playing:{" "}
          <span className="text-black dark:text-gray-200 ml-1.5">
            {currentTitle ? `${currentTitle}.mp4` : info?.name}
          </span>
        </p>
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
