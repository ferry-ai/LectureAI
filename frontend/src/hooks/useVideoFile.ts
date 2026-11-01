import { useCallback, useEffect, useRef, useState } from "react";

export function useVideoFile() {
  const [url, setUrl] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const timeRef = useRef(0);
  const urlRef = useRef<string | null>(null);

  const load = useCallback((files: File[]) => {
    const video = files.find(isVideoFile);
    if (!video) return;
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    const next = URL.createObjectURL(video);
    urlRef.current = next;
    timeRef.current = 0;
    setUrl(next);
    setName(video.name);
  }, []);

  useEffect(() => {
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  return {
    url,
    name,
    resumeAt: timeRef,
    load,
    rememberTime: (time: number) => {
      timeRef.current = time;
    },
  };
}

function isVideoFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  return /\.(mp4|webm|mov|mkv|ogv|ogg|m4v)$/i.test(file.name);
}
