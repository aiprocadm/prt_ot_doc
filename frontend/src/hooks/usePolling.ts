import { useEffect, useRef } from "react";

type UsePollingOptions = {
  enabled?: boolean;
  runImmediately?: boolean;
  onError?: (error: unknown) => void;
};

export const usePolling = (
  callback: () => void | Promise<void>,
  interval: number,
  enabledOrOptions: boolean | UsePollingOptions = true,
) => {
  const savedCallback = useRef(callback);
  const inFlight = useRef(false);
  const onErrorRef = useRef<UsePollingOptions["onError"]>(undefined);

  const options: UsePollingOptions =
    typeof enabledOrOptions === "boolean"
      ? { enabled: enabledOrOptions }
      : enabledOrOptions;
  const enabled = options.enabled ?? true;
  const runImmediately = options.runImmediately ?? false;

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    onErrorRef.current = options.onError;
  }, [options.onError]);

  useEffect(() => {
    if (!enabled) return undefined;

    const tick = async () => {
      if (inFlight.current) return;

      inFlight.current = true;
      try {
        await savedCallback.current();
      } catch (error) {
        onErrorRef.current?.(error);
      } finally {
        inFlight.current = false;
      }
    };

    if (runImmediately) {
      void tick();
    }
    const intervalId = window.setInterval(() => {
      void tick();
    }, interval);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, interval, runImmediately]);
};
