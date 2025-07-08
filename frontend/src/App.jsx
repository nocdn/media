import React, { useEffect, useState } from "react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [mediaList, setMediaList] = useState([]);
  const [currentTitle, setCurrentTitle] = useState(null);
  const [hasSubtitle, setHasSubtitle] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("http://localhost:8000/current");
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
      const res = await fetch("http://localhost:8000/media");
      if (res.ok) {
        const data = await res.json();
        setMediaList(data.files || []);
      }
    } catch (_) {}
  };

  const toggleMenu = () => {
    if (!showMenu && mediaList.length === 0) {
      fetchMedia();
    }
    setShowMenu(!showMenu);
  };

  const selectVideo = async (title) => {
    setShowMenu(false);
    setProcessing(false);
    setCurrentTitle(title);
    try {
      const res = await fetch(`http://localhost:8000/subtitle/${title}`, {
        method: "HEAD",
      });
      setHasSubtitle(res.ok);
    } catch {
      setHasSubtitle(false);
    }
  };

  const videoSrc = currentTitle
    ? `http://localhost:8000/video/${currentTitle}`
    : `http://localhost:8000/video`;
  const subtitleSrc = currentTitle
    ? `http://localhost:8000/subtitle/${currentTitle}`
    : `http://localhost:8000/subtitle`;

  return (
    <div className="p-4 font-geist relative">
      <h1 className="mb-0 font-semibold font-geist">video stream</h1>
      {processing && (
        <p className="text-sm text-yellow-400 mt-1 mb-3">processing video…</p>
      )}

      {info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center">
          playing:{" "}
          <span className="text-black dark:text-gray-200">
            {currentTitle ? `${currentTitle}.mp4` : info?.name}
          </span>
          <span
            className="ml-auto cursor-pointer hover:text-black"
            onClick={toggleMenu}
          >
            watch something else
          </span>
        </p>
      )}

      {!processing && (
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
      )}

      {showMenu && (
        <div className="absolute top-16 right-0 w-64 h-[480px] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow overflow-y-auto rounded-md p-2">
          {mediaList.map((name) => (
            <div
              key={name}
              className="px-2 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              onClick={() => selectVideo(name)}
            >
              {name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
