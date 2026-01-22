import { AlertTriangle } from "lucide-react";

import type { ApiError } from "@/types/dto/common";

export const ErrorState = ({ error, onRetry }: { error?: ApiError | null; onRetry?: () => void }) => {
  if (!error) return null;
  return (
    <div className="flex flex-col items-center justify-center space-y-2 rounded-md border border-destructive/40 bg-destructive/10 p-6 text-center text-destructive">
      <AlertTriangle className="h-8 w-8" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold">{error.message}</p>
        {error.code && <p className="text-xs">Код: {error.code}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          className="text-sm font-medium text-destructive underline-offset-4 hover:underline"
          onClick={onRetry}
        >
          Повторить
        </button>
      )}
    </div>
  );
};
