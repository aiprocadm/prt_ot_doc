import { useCallback, useEffect, useState } from "react";

import type { ApiError } from "@/types/dto/common";

type AsyncResourceOptions<TData> = {
  loader: () => Promise<TData>;
  initialData: TData;
  errorMessage: string;
};

const normalizeApiError = (error: unknown, fallbackMessage: string): ApiError => {
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error as ApiError;
  }
  return { status: 0, message: fallbackMessage };
};

export const useAsyncResource = <TData>({ loader, initialData, errorMessage }: AsyncResourceOptions<TData>) => {
  const [data, setData] = useState<TData>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await loader();
      setData(next);
      return next;
    } catch (err) {
      const normalized = normalizeApiError(err, errorMessage);
      setError(normalized);
      throw normalized;
    } finally {
      setLoading(false);
    }
  }, [errorMessage, loader]);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  return { data, setData, loading, error, reload };
};
