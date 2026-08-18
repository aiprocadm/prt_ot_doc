import type { TrafficLight } from "@/api/managedClients";

/**
 * Светофор соответствия (BIZ-51, разд. 51.3) — словари представления.
 * Общие для кокпита и карточки клиента: два словаря разошлись бы в подписи
 * одного и того же цвета на соседних экранах.
 *
 * Цвет продублирован СЛОВОМ намеренно: бейдж читается и без различения
 * цветов, и в чёрно-белой распечатке.
 */
export const LIGHT_LABELS: Record<TrafficLight, string> = {
  green: "В порядке",
  yellow: "Истекает",
  red: "Разрывы",
  not_measured: "Не измеряется",
};

export const LIGHT_VARIANT: Record<
  TrafficLight,
  "default" | "destructive" | "secondary" | "outline"
> = {
  red: "destructive",
  yellow: "default",
  green: "secondary",
  not_measured: "outline",
};

/** Подпись итога отчёта/светофора; незнакомое значение показываем как есть. */
export const lightLabel = (value: string): string =>
  LIGHT_LABELS[value as TrafficLight] ?? value;

export const lightVariant = (
  value: string,
): "default" | "destructive" | "secondary" | "outline" =>
  LIGHT_VARIANT[value as TrafficLight] ?? "outline";
