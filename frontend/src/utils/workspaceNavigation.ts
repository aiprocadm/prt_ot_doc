export const taskInboxLink = (task: {
  id?: string;
  overdue: boolean;
  priority: string;
  entity_type?: string | null;
  entity_id?: string | null;
}) => {
  const params = new URLSearchParams();
  if (task.overdue) {
    params.set("overdue", "true");
  }
  if (["low", "medium", "high", "critical"].includes(task.priority)) {
    params.set("priority", task.priority);
  }
  if (task.id) {
    params.set("task_id", task.id);
  }
  if (task.entity_type) {
    params.set("entity_type", task.entity_type);
  }
  if (task.entity_id) {
    params.set("entity_id", task.entity_id);
  }
  const query = params.toString();
  return query ? `/tasks?${query}` : "/tasks";
};

export const entityContextPath = (entityType: string | null | undefined) => {
  switch (entityType) {
    case "inspection":
      return "/inspections";
    case "incident":
      return "/incidents";
    case "training_plan":
    case "training_enrollment":
      return "/training";
    case "ppe_issue":
      return "/ppe";
    // Срез-156: было `/contracts` — маршрута с таким путём нет, и человек с
    // дашборда молча уезжал на посадочную страницу по catch-all. Договоры
    // живут на экране финансов («реальные договоры, заказы, счета»).
    case "contract":
      return "/crm-finance";
    case "template_version":
    case "document":
    case "document_version":
      return "/documents";
    case "person":
      return "/persons";
    case "company":
    case "site":
      return "/companies";
    case "task":
      return "/tasks";
    case "compliance_deadline":
      return "/tasks?overdue=true";
    default:
      return null;
  }
};

export const entityCardLink = (
  entityType: string | null | undefined,
  entityId: string | null | undefined,
  view: "summary" | "timeline" = "summary",
) => {
  if (!entityType || !entityId) return null;

  switch (entityType) {
    case "document":
    case "document_version":
    case "template_version": {
      const params = new URLSearchParams({
        entity_type: entityType,
        entity_id: entityId,
        view,
      });
      return `/documents?${params.toString()}`;
    }
    // Срез-156: `contract` убран из этой ветки. Она открывает карточку на
    // экране ПОДРЯДЧИКОВ, а договор — сущность финансов; экран подрядчиков
    // параметров `entity_type`/`entity_id` не читает вовсе, то есть карточка
    // договора там не открылась бы. Ссылки «карточка» для договора нет, а
    // переход в контекст (`entityContextPath`) ведёт на экран финансов.
    case "company":
    case "site": {
      const params = new URLSearchParams({
        entity_type: entityType,
        entity_id: entityId,
        view,
      });
      return `/contractors?${params.toString()}`;
    }
    case "inspection": {
      const params = new URLSearchParams({
        entity_type: entityType,
        entity_id: entityId,
        view,
      });
      return `/inspections?${params.toString()}`;
    }
    default:
      return null;
  }
};

const BLOCKER_LINKS: Record<string, string> = {
  employees_missing_contacts: "/persons",
  templates_not_ready: "/templates",
  training_overdue: "/tasks?type=training_plan&overdue=true",
  ppe_expired: "/ppe",
  // Срез-156: тот же несуществующий `/contracts`, что и выше. Блокер
  // «истекли договоры» вёл человека на посадочную страницу вместо
  // экрана, где договоры видны.
  contracts_expired: "/crm-finance",
};

/** Подпись ссылки «куда исправлять» — понятнее общего «Открыть рабочий экран». */
const BLOCKER_ACTION_LABELS: Record<string, string> = {
  employees_missing_contacts: "Открыть реестр сотрудников",
  templates_not_ready: "Открыть шаблоны",
  training_overdue: "Открыть задачи по обучению",
  ppe_expired: "Открыть СИЗ",
  contracts_expired: "Открыть договоры",
};

export const blockerActionPath = (blockerCode: string, entityType: string) => {
  return BLOCKER_LINKS[blockerCode] ?? entityContextPath(entityType) ?? "/";
};

export const blockerActionLabel = (blockerCode: string) =>
  BLOCKER_ACTION_LABELS[blockerCode] ?? "Открыть рабочий экран";
