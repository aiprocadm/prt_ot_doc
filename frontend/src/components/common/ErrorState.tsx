import { AlertTriangle } from "lucide-react";

import type { ApiError } from "@/types/dto/common";

export const ErrorState = ({ error, onRetry }: { error?: ApiError | null; onRetry?: () => void }) => {
  if (!error) return null;

  return (
    <div
      className="flex flex-col items-center justify-center space-y-2 rounded-md border border-destructive/40 bg-destructive/10 p-6 text-center text-destructive"
      role="alert"
      aria-live="polite"
    >
      <AlertTriangle className="h-8 w-8" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-sm font-semibold">{error.message}</p>
        {error.code && <p className="text-xs">Код: {error.code}</p>}
        {error.correlation_id && <p className="text-xs">Correlation ID: {error.correlation_id}</p>}
        {error.field_errors?.length ? (
          <ul className="list-disc space-y-1 pl-5 text-left text-xs">
            {error.field_errors.map((fieldError) => (
              <li key={`${fieldError.field}:${fieldError.code ?? fieldError.message}`}>
                <span className="font-medium">{fieldError.field}:</span> {fieldError.message}
              </li>
            ))}
          </ul>
        ) : null}
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
