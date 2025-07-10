import React, { useEffect, useState } from "react";
import { CirclePlay } from "lucide-react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [showMenu, setShowMenu] = useState(true);
  const [mediaList, setMediaList] = useState([]);
  const [currentTitle, setCurrentTitle] = useState(null);
  const [hasSubtitle, setHasSubtitle] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/current");
        if (!res.ok) return;
        const data = await res.json();
        if (data.processing) {
          setProcessing(true);
        } else {
          setProcessing(false);
          setInfo(data);
          setCurrentTitle(data.title ?? data.name.replace(/\.mp4$/, ""));
          setHasSubtitle(!!data.subtitle);
        }
      } catch (_) {}
    };

    load();

    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  const fetchMedia = async () => {
    try {
      const res = await fetch("/api/media");
      if (res.ok) {
        const data = await res.json();
        setMediaList(data.files || []);
      }
    } catch (_) {}
  };

  const toggleMenu = () => {
    if (mediaList.length === 0) {
      fetchMedia();
    }
  };

  const selectVideo = async (title) => {
    setShowMenu(false);
    setProcessing(false);
    setCurrentTitle(title);
    try {
      const res = await fetch(`/api/subtitle/${title}`, {
        method: "HEAD",
      });
      setHasSubtitle(res.ok);
    } catch {
      setHasSubtitle(false);
    }
  };

  const videoSrc = currentTitle ? `/api/video/${currentTitle}` : `/api/video`;
  const subtitleSrc = currentTitle
    ? `/api/subtitle/${currentTitle}`
    : `/api/subtitle`;

  return (
    <div className="p-4 font-geist relative">
      <h1 className="mb-0 font-semibold font-geist">video stream</h1>
      {processing && (
        <p className="text-sm text-yellow-400 mt-1 mb-3">processing video…</p>
      )}

      {info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center">
          playing:{" "}
          <span className="text-black dark:text-gray-200 ml-1.5">
            {currentTitle ? `${currentTitle}.mp4` : info?.name}
          </span>
          <span
            className="ml-auto cursor-pointer hover:text-black mr-2"
            onClick={toggleMenu}
            style={{
              display: mediaList.length > 0 ? "none" : "inline",
            }}
          >
            watch something else
          </span>
        </p>
      )}

      {!processing && (
        <div className="flex justify-center">
          <video
            width="860"
            controls
            src={videoSrc}
            className="rounded-md"
            crossOrigin="anonymous"
          >
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
