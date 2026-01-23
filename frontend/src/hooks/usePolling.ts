import { useEffect, useRef } from "react";

export const usePolling = (callback: () => void, interval: number, enabled = true) => {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return undefined;
    const id = window.setInterval(() => savedCallback.current(), interval);
    return () => window.clearInterval(id);
  }, [interval, enabled]);
};
