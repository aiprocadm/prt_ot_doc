import { AlertTriangle } from "lucide-react";

import type { ApiError } from "@/types/dto/common";

const resolveUserMessage = (error: ApiError): string => {
  if (error.status >= 500 || error.code === "INTERNAL_ERROR") {
    return "Сервер временно не отвечает. Нажмите «Повторить» или обновите страницу.";
  }
  return error.message?.trim() || "Не удалось выполнить запрос.";
};

const serverSupportLine = (error: ApiError): string | null => {
  const parts: string[] = [];
  if (error.code) parts.push(error.code);
  if (error.correlation_id) parts.push(error.correlation_id);
  return parts.length ? parts.join(" · ") : null;
};

export const ErrorState = ({ error, onRetry }: { error?: ApiError | null; onRetry?: () => void }) => {
  if (!error) return null;

  const isServerSide = error.status >= 500 || error.code === "INTERNAL_ERROR";
  const supportLine = isServerSide ? serverSupportLine(error) : null;
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
        {supportLine ? (
          <p className="break-all font-mono text-[11px] opacity-75" title="Передайте строку в поддержку при обращении">
            {supportLine}
          </p>
        ) : null}
        {!isServerSide && error.code ? <p className="text-xs opacity-90">Код: {error.code}</p> : null}
        {!isServerSide && error.correlation_id ? (
          <p className="text-xs opacity-90">ID корреляции: {error.correlation_id}</p>
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
