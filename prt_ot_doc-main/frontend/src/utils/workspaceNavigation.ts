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
    case "contract":
      return "/contracts";
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
  view: "summary" | "timeline" = "summary"
) => {
  if (!entityType || !entityId) return null;

  switch (entityType) {
    case "document":
    case "document_version":
    case "template_version": {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId, view });
      return `/documents?${params.toString()}`;
    }
    case "company":
    case "site":
    case "contract": {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId, view });
      return `/contractors?${params.toString()}`;
    }
    case "inspection": {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId, view });
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
  contracts_expired: "/contracts",
};

export const blockerActionPath = (blockerCode: string, entityType: string) => {
  return BLOCKER_LINKS[blockerCode] ?? entityContextPath(entityType) ?? "/";
};
