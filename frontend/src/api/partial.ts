import type { ApiError } from "@/types/dto/common";

/**
 * Срез-167: часть экрана может быть закрыта правами, и это не повод гасить
 * весь экран.
 *
 * Сводные экраны грузят несколько списков одним пакетом. Пакет отклоняется
 * целиком, если отклонён хоть один запрос, поэтому один отказ по правам
 * оставлял человека перед пустой страницей с общей ошибкой — даже когда
 * остальные списки ему доступны.
 *
 * Здесь перехватывается ТОЛЬКО отказ по правам (403). Всё остальное —
 * недоступный сервер, ошибка внутри него, разрыв связи — проходит наверх без
 * изменений: это поломка, и прятать её нельзя.
 *
 * Молча подставлять пустоту тоже нельзя: пустой список и «сюда вам нельзя» —
 * разные вещи, а выглядят одинаково. Поэтому каждый перехват записывает
 * название раздела, и экран обязан сказать о нём словами.
 */

const isForbidden = (error: unknown): boolean => {
  const status = (error as ApiError | undefined)?.status;
  return status === 403;
};

export type PartialLoad = {
  /** Названия разделов, закрытых правами. */
  denied: string[];
};

/**
 * Выполняет запрос; при отказе по правам возвращает запасное значение и
 * записывает название раздела в `state.denied`.
 */
export const allowedOr = async <T>(
  state: PartialLoad,
  section: string,
  request: Promise<T>,
  fallback: T,
): Promise<T> => {
  try {
    return await request;
  } catch (error) {
    if (isForbidden(error)) {
      if (!state.denied.includes(section)) {
        state.denied.push(section);
      }
      return fallback;
    }
    throw error;
  }
};

/** Фраза для экрана: чего человек не видит и почему. */
export const deniedNotice = (denied?: string[] | null): string | null => {
  if (!denied?.length) return null;
  const list = denied.join(", ");
  return `Часть данных скрыта: у вашей роли нет доступа к разделам — ${list}. Остальное показано полностью.`;
};
