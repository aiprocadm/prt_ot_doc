import { apiClient } from "@/api/client";

export type TopNavKpi = {
  tasks: number;
  alerts: number;
};

export const getTopNavKpi = async (): Promise<TopNavKpi> => {
  const [taskResponse, notificationResponse] = await Promise.all([
    apiClient.get<Array<unknown>>("/workflow/tasks", {
      params: { assignee: "me" },
    }),
    apiClient.get<{ unread_count: number }>("/notifications", {
      params: { status: "unread", limit: 1 },
    }),
  ]);

  return {
    tasks: taskResponse.data.length,
    alerts: notificationResponse.data.unread_count ?? 0,
  };
};

// СРЕЗ-233: здесь была отправка UX-метрик на `POST /analytics/ux-events`.
//
// Такого маршрута у сервера НЕТ и не было: запрос уходил при КАЖДОМ переходе
// между экранами и всегда получал 404. Ошибку глушили, а рядом лежал тест с
// названием «не показывает тост при 404: эндпоинт может отсутствовать» — то
// есть отсутствие приёмника было закреплено как норма.
//
// Отправку убрали, сбор оставили: он работает и хранит события в браузере
// (`utils/uxMetrics.ts`, там же честно записано, что читателя у них пока нет).
// Завести приёмник — отдельная работа с решениями о хранении и сроках, и это
// решение владельца, а не побочный эффект починки.
//
// Сторож `tests/test_frontend_calls_existing_routes.py` не даёт витрине снова
// звать адрес, которого у сервера нет.
