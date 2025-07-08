import React, { useEffect, useState } from "react";

export default function App() {
  const [info, setInfo] = useState(null);
  const [processing, setProcessing] = useState(false);

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
        }
      } catch (_) {}
    };

    load();

    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="p-4 font-geist">
      <h1 className="mb-0 font-semibold font-geist">video stream</h1>
      {processing && (
        <p className="text-sm text-yellow-400 mt-1 mb-3">processing video…</p>
      )}

      {info && !processing && (
        <p className="text-sm text-gray-500 mt-1 font-jetbrains-mono font-medium mb-3 flex items-center">
          playing:{" "}
          <span className="text-black dark:text-gray-200">{info.name}</span>
          <span className="ml-auto">watch something else</span>
        </p>
      )}

      {!processing && (
        <video
          width="860"
          controls
          src={`http://localhost:8000/video`}
          className="rounded-md"
          crossOrigin="anonymous"
        >
          {info?.subtitle && (
            <track
              label="Subtitles"
              kind="subtitles"
              srcLang="en"
              src="http://localhost:8000/subtitle"
              default
            />
          )}
        </video>
      )}
    </div>
  );
}
