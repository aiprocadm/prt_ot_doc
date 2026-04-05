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
  critical: "destructive",
  error: "destructive",
  failed: "destructive",
  cancelled: "destructive",
  archived: "destructive"
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
  critical: "Критично",
  error: "Ошибка",
  failed: "Сбой",
  cancelled: "Отменено",
  archived: "В архиве",
  dismissed: "Снято",
  suspended: "Приостановлен",
  terminated: "Прекращён",
  on_leave: "В отпуске"
};

export const StatusBadge = ({ status }: { status?: string | null }) => {
  if (!status) return null;
  const variant = statusColors[status] ?? "secondary";
  const label = statusLabelsRu[status] ?? status;
  return <Badge variant={variant}>{label}</Badge>;
};
