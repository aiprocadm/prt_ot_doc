import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError } from "@/types/dto/common";

type AsyncResourceOptions<TData> = {
  loader: () => Promise<TData>;
  initialData: TData;
  errorMessage: string;
  /** При ошибке: при возврате на вкладку браузера выполнить повторную загрузку */
  refetchOnVisibleAfterError?: boolean;
};

const normalizeApiError = (
  error: unknown,
  fallbackMessage: string,
): ApiError => {
  if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error as ApiError;
  }
  return { status: 0, message: fallbackMessage };
};

export const useAsyncResource = <TData>({
  loader,
  initialData,
  errorMessage,
  refetchOnVisibleAfterError = true,
}: AsyncResourceOptions<TData>) => {
  const [data, setData] = useState<TData>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const errorRef = useRef<ApiError | null>(null);
  errorRef.current = error;
  const seqRef = useRef(0);

  const reload = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      const next = await loader();
      if (seq === seqRef.current) {
        setData(next);
      }
      return next;
    } catch (err) {
      const normalized = normalizeApiError(err, errorMessage);
      if (seq === seqRef.current) {
        setError(normalized);
      }
      throw normalized;
    } finally {
      if (seq === seqRef.current) {
        setLoading(false);
      }
    }
  }, [errorMessage, loader]);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  useEffect(() => {
    if (!refetchOnVisibleAfterError) return;
    const onVisible = () => {
      if (document.visibilityState !== "visible" || !errorRef.current) return;
      void reload().catch(() => undefined);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refetchOnVisibleAfterError, reload]);

  return { data, setData, loading, error, reload };
};
