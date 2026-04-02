import { useEffect, useRef } from "react";

type UsePollingOptions = {
  enabled?: boolean;
  runImmediately?: boolean;
  onError?: (error: unknown) => void;
};

export const usePolling = (
  callback: () => void | Promise<void>,
  interval: number,
  enabledOrOptions: boolean | UsePollingOptions = true
) => {
  const savedCallback = useRef(callback);
  const inFlight = useRef(false);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    const options: UsePollingOptions =
      typeof enabledOrOptions === "boolean" ? { enabled: enabledOrOptions } : enabledOrOptions;
    const enabled = options.enabled ?? true;

    if (!enabled) return undefined;

    const tick = async () => {
      if (inFlight.current) return;

      inFlight.current = true;
      try {
        await savedCallback.current();
      } catch (error) {
        options.onError?.(error);
      } finally {
        inFlight.current = false;
      }
    };

    if (options.runImmediately) {
      void tick();
    }
    const intervalId = window.setInterval(() => {
      void tick();
    }, interval);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [interval, enabledOrOptions]);
};
