import { AlertTriangle } from "lucide-react";

import type { ApiError } from "@/types/dto/common";

const resolveUserMessage = (error: ApiError): string => {
  if (error.code === "INTERNAL_ERROR" || (error.status >= 500 && !error.message?.trim())) {
    return "На сервере произошла ошибка. Часто помогает повторить запрос или подождать несколько секунд.";
  }
  return error.message?.trim() || "Не удалось выполнить запрос.";
};

export const ErrorState = ({ error, onRetry }: { error?: ApiError | null; onRetry?: () => void }) => {
  if (!error) return null;

  const isServerSide = error.status >= 500 || error.code === "INTERNAL_ERROR";
  const surfaceClass = isServerSide
    ? "border-amber-500/40 bg-amber-50 text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50"
    : "border-destructive/40 bg-destructive/10 text-destructive";

  return (
    <div
      className={`flex flex-col items-center justify-center space-y-2 rounded-md border p-6 text-center ${surfaceClass}`}
      role="alert"
      aria-live="polite"
    >
      <AlertTriangle className="h-8 w-8" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-sm font-semibold">{resolveUserMessage(error)}</p>
        {error.code && <p className="text-xs opacity-90">Код: {error.code}</p>}
        {error.correlation_id && <p className="text-xs opacity-90">Correlation ID: {error.correlation_id}</p>}
        {isServerSide ? (
          <p className="text-xs opacity-80">
            Если ошибка появилась после переключения вкладки браузера, вернитесь на приложение и нажмите «Повторить».
          </p>
        ) : null}
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
          className={`text-sm font-medium underline-offset-4 hover:underline ${isServerSide ? "text-amber-900 dark:text-amber-100" : "text-destructive"}`}
          onClick={onRetry}
        >
          Повторить
        </button>
      )}
    </div>
  );
};
