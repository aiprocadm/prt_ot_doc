import type { FieldPath, FieldValues, UseFormSetError } from "react-hook-form";

import type { ApiError } from "@/types/dto/common";

/** Проверяет, является ли пойманная ошибка нормализованным `ApiError` (содержит `message: string`). */
export function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as ApiError).message === "string"
  );
}

/**
 * Приводит любую пойманную ошибку к ApiError.
 * Используется вместо `error as ApiError` во всех сторах.
 */
export function normalizeError(error: unknown): ApiError {
  if (isApiError(error)) return error;
  const message = error instanceof Error ? error.message : "Unknown error";
  return { status: 0, message, field_errors: [] };
}

/** Сопоставляет имена полей из ответа валидации API с полями react-hook-form. */
export function applyApiFieldErrorsToForm<T extends FieldValues>(
  setError: UseFormSetError<T>,
  error: ApiError,
  map: Record<string, FieldPath<T>>,
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
