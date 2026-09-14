import { Badge } from "@/components/ui/badge";

const statusColors: Record<string, "default" | "secondary" | "destructive"> = {
  active: "default",
  ready: "default",
  published: "default",
  draft: "secondary",
  generating: "secondary",
  processing: "secondary",
  queued: "secondary",
  open: "secondary",
  in_progress: "secondary",
  done: "default",
  ok: "default",
  warning: "secondary",
  degraded: "secondary",
  critical: "destructive",
  error: "destructive",
  failed: "destructive",
  cancelled: "destructive",
  archived: "destructive",
  issued: "default",
  closed: "secondary",
  overdue: "destructive",
  missing: "destructive",
  due_soon: "secondary",
  scheduled: "secondary",
  completed: "default",
  lifted: "secondary",
  submitted: "secondary",
  approved: "default",
  rejected: "destructive",
  paid: "default",
  // Срез-161: статусы исходящих доставок (OutboxStatus). Без них значок был
  // серым и показывал код латиницей.
  pending: "secondary",
  sent: "default",
  dead: "destructive",
};

/** Подписи для типичных статусов API; неизвестные значения показываем как есть. */
const statusLabelsRu: Record<string, string> = {
  active: "Активен",
  inactive: "Неактивен",
  ready: "Готов",
  published: "Опубликован",
  draft: "Черновик",
  generating: "Генерация",
  processing: "Обработка",
  queued: "В очереди",
  open: "Открыта",
  in_progress: "В работе",
  done: "Выполнено",
  ok: "ОК",
  warning: "Внимание",
  degraded: "Деградация",
  critical: "Критично",
  error: "Ошибка",
  failed: "Сбой",
  cancelled: "Отменено",
  archived: "В архиве",
  dismissed: "Снято",
  suspended: "Приостановлен",
  terminated: "Прекращён",
  on_leave: "В отпуске",
  issued: "Выдан",
  closed: "Закрыт",
  overdue: "Просрочен",
  due_soon: "Истекает",
  missing: "Отсутствует",
  scheduled: "Запланировано",
  completed: "Завершено",
  lifted: "Снято",
  // Заявки на возмещение СФР (§12.4 срез-2); draft уже выше — «Черновик».
  submitted: "Подана",
  approved: "Одобрена",
  rejected: "Отклонена",
  paid: "Выплачена",
  // Срез-161: статусы исходящих доставок (OutboxStatus).
  pending: "Ожидание",
  sent: "Отправлено",
  dead: "Окончательный сбой",
};

/**
 * Срез-180: важность задачи и письма (`TaskPriority`, `NotificationPriority` —
 * значения совпадают). Рядом со статусами, потому что печатается там же.
 */
const priorityLabelsRu: Record<string, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая",
};

/**
 * Подпись статуса ДЛЯ ТЕКСТА (не значка).
 *
 * Срез-180: тот же словарь, что у значка, нужен в местах, где компонент
 * поставить нельзя — строка списка, пункт выпадающего списка, предложение.
 * Раньше там печатали сам код, и человек видел латиницу вроде `draft` или
 * `PENDING`. Неизвестное значение возвращается как есть: молчать о нём нельзя.
 */
export const statusLabel = (status?: string | null): string => {
  if (!status) return "—";
  return statusLabelsRu[status.toLowerCase()] ?? status;
};

/** Подпись важности для текста; неизвестное значение — как есть. */
export const priorityLabel = (priority?: string | null): string => {
  if (!priority) return "—";
  return priorityLabelsRu[priority.toLowerCase()] ?? priority;
};

export const StatusBadge = ({ status }: { status?: string | null }) => {
  if (!status) return null;
  // Срез-161: часть ручек отдаёт статус ПРОПИСНЫМИ (`FAILED`, `DEAD` —
  // перечисление OutboxStatus). Раньше поиск шёл по строке как есть, и такой
  // статус показывался кодом латиницей серым значком вместо «Сбой» красным.
  const key = status.toLowerCase();
  const variant = statusColors[key] ?? "secondary";
  const label = statusLabelsRu[key] ?? status;
  return <Badge variant={variant}>{label}</Badge>;
};
