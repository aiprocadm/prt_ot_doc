import type { FieldPath, FieldValues, UseFormSetError } from "react-hook-form";

import type { ApiError } from "@/types/dto/common";

export function isApiError(err: unknown): err is ApiError {
  return typeof err === "object" && err !== null && typeof (err as ApiError).message === "string";
}

/** Сообщение для тоста / шапки: приоритет у field_errors от API. */
export function formatApiErrorMessage(err: unknown, fallback: string): string {
  if (!isApiError(err)) return fallback;
  const fe = err.field_errors?.filter((f) => f.field && f.message) ?? [];
  if (fe.length > 0) {
    return fe.map((f) => `${f.field}: ${f.message}`).join(" • ");
  }
  if (err.message === "Request validation failed") {
    return "Данные не прошли проверку на сервере. Проверьте поля формы.";
  }
  return err.message || fallback;
}

/** Сопоставляет имена полей из ответа валидации API с полями react-hook-form. */
export function applyApiFieldErrorsToForm<T extends FieldValues>(
  setError: UseFormSetError<T>,
  error: ApiError,
  map: Record<string, FieldPath<T>>
): void {
  const seen = new Set<string>();
  for (const fe of error.field_errors ?? []) {
    if (!fe.field || !fe.message) continue;
    const normalized = fe.field.replace(/^body\./, "");
    const formKey = map[normalized] ?? map[fe.field];
    if (!formKey) continue;
    const key = String(formKey);
    if (seen.has(key)) continue;
    seen.add(key);
    setError(formKey, { type: "server", message: fe.message });
  }
}
