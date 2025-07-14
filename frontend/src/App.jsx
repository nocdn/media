import React, { useEffect, useState, useRef } from "react";
import { CirclePlay } from "lucide-react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [mediaList, setMediaList] = useState([]);
  const [currentTitle, setCurrentTitle] = useState(null);
  const [hasSubtitle, setHasSubtitle] = useState(false);

  const pollRef = useRef(null);
  const videoRef = useRef(null);

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
    try {
      const res = await fetch("/api/media");
      if (res.ok) {
        const data = await res.json();
        setMediaList(data.files || []);
      }
    } catch (_) {}
  };

  // ---------- effects ----------

  // start / stop polling
  useEffect(() => {
    pollCurrent();
    pollRef.current = setInterval(pollCurrent, 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  // whenever title changes → reload video element
  useEffect(() => {
    if (videoRef.current) {
      console.debug("🔁 switching to", currentTitle ?? "latest");
      videoRef.current.load();
    }
  }, [currentTitle]);

  // ---------- ui handlers ----------

  const selectVideo = async (title) => {
    clearInterval(pollRef.current);
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

      {info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center">
          playing:{" "}
          <span className="text-black dark:text-gray-200 ml-1.5">
            {currentTitle ? `${currentTitle}.mp4` : info?.name}
          </span>
          {mediaList.length === 0 && (
            <span
              className="ml-auto cursor-pointer hover:text-black mr-2"
              onClick={fetchMedia}
            >
              watch something else
            </span>
          )}
        </p>
      )}

      {!processing && (
        <div className="flex justify-center">
          <video
            key={currentTitle || "latest"} // force remount when title changes
            ref={videoRef}
            width="860"
            controls
            className="rounded-md"
            crossOrigin="anonymous"
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
            {mediaList.length > 0 && (
              <p className="font-jetbrains-mono text-gray-600 font-semibold text-[15px] pl-1.5 mb-1.5">
                AVAILABLE MEDIA{" "}
                <span className="text-gray-400">(click any to play)</span>
              </p>
            )}
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
    </div>
  );
}
