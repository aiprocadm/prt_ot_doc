/**
 * Замеры удобства работы: сколько прошло до первого действия, как часто человек
 * возвращается назад, доходит ли он от пустого экрана до действия.
 *
 * ГДЕ ОНИ ОКАЗЫВАЮТСЯ (срез-233, названо честно). События копятся В БРАУЗЕРЕ
 * ЧЕЛОВЕКА — в его локальном хранилище, кольцом на 200 последних. На сервер они
 * НЕ уходят и читателя у них пока НЕТ.
 *
 * До среза-233 к сбору была привязана отправка на `POST /analytics/ux-events`.
 * Такого маршрута у сервера нет и не было: запрос уходил при каждом переходе
 * между экранами и всегда получал 404, а ошибку глушили. Отправку убрали —
 * толку от неё не было, а цена была в запросе на каждый переход.
 *
 * ЧТО ЭТО ЗНАЧИТ ДЛЯ ТРЕБОВАНИЯ. Числовой UX-бюджет экрана (ТЗ разд. 59)
 * держится НЕ этими замерами, а статической проверкой `src/ux/budget.ts` и её
 * тестами — она живая. Здешние замеры были задуманы сверх того.
 *
 * ЧТОБЫ ОНИ НАЧАЛИ РАБОТАТЬ, нужен приёмник на сервере: маршрут, хранение,
 * срок жизни записей и ответ на вопрос, чьи это данные. Это решение владельца,
 * а не побочный эффект починки.
 */
import {
  localStorageGetItem,
  localStorageSetItem,
} from "@/utils/browserStorage";

const UX_METRICS_STORAGE_KEY = "ux.metrics.events.v1";
const MAX_EVENTS = 200;

export type UxMetricEvent = {
  name:
    | "time_to_first_action"
    | "nav_backtrack_rate"
    | "empty_state_to_action_rate"
    | "navigation_click"
    | "route_view";
  ts: number;
  payload?: Record<string, string | number | boolean | null | undefined>;
};

const readEvents = (): UxMetricEvent[] => {
  const raw = localStorageGetItem(UX_METRICS_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as UxMetricEvent[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeEvents = (events: UxMetricEvent[]) => {
  localStorageSetItem(
    UX_METRICS_STORAGE_KEY,
    JSON.stringify(events.slice(-MAX_EVENTS)),
  );
};

export const trackUxMetric = (
  name: UxMetricEvent["name"],
  payload?: UxMetricEvent["payload"],
) => {
  const events = readEvents();
  events.push({ name, ts: Date.now(), payload });
  writeEvents(events);
};
