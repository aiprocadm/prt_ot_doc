import {
  AlertTriangle,
  FileText,
  ListChecks,
  PlayCircle,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

const quickActions: Array<{
  label: string;
  icon: typeof FileText;
  permission: Permission;
  to: string;
}> = [
  {
    label: "Создать документ",
    icon: FileText,
    permission: PERMISSIONS.DOCUMENT_CREATE,
    to: "/documents/wizard",
  },
  {
    label: "Запустить мастер",
    icon: PlayCircle,
    permission: PERMISSIONS.PACK_VIEW,
    to: "/packs",
  },
  {
    label: "Назначить обучение",
    icon: ListChecks,
    permission: PERMISSIONS.TRAINING_ASSIGN,
    to: "/training",
  },
  {
    label: "Выдать СИЗ",
    icon: Users,
    permission: PERMISSIONS.PPE_ISSUE,
    to: "/ppe",
  },
];

const statusItems = [
  {
    label: "Согласования сегодня",
    value: "18",
    tone: "default",
    to: "/approvals/inbox",
  },
  {
    label: "Просрочки обучений",
    value: "7",
    tone: "destructive",
    to: "/training",
  },
  {
    label: "Предписания к закрытию",
    value: "4",
    tone: "secondary",
    to: "/prescriptions",
  },
];

export const RightDrawer = () => {
  const { can } = useAbility();
  const visibleActions = quickActions.filter((action) =>
    can(action.permission),
  );

  return (
    <aside className="hidden w-72 flex-shrink-0 space-y-6 border-l bg-muted/20 p-4 xl:sticky xl:top-20 xl:block xl:self-start">
      {visibleActions.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Быстрые действия
          </h2>
          <div className="mt-3 space-y-2">
            {visibleActions.map((action) => (
              <Button
                key={action.label}
                variant="outline"
                className="w-full justify-start gap-2"
                asChild
              >
                <Link to={action.to}>
                  <action.icon className="h-4 w-4" />
                  {action.label}
                </Link>
              </Button>
            ))}
          </div>
        </div>
      )}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Сводка дня
        </h2>
        <div className="mt-3 space-y-2 text-sm">
          {statusItems.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              className="flex items-center justify-between rounded-md border bg-background px-3 py-2 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span>{item.label}</span>
              <Badge
                variant={item.tone as "default" | "secondary" | "destructive"}
              >
                {item.value}
              </Badge>
            </Link>
          ))}
        </div>
      </div>
      <div className="rounded-md border border-dashed bg-background p-3 text-sm text-muted-foreground">
        <div className="flex items-center gap-2 text-foreground">
          <AlertTriangle className="h-4 w-4 text-destructive" />
          Триггер пересмотра рисков
        </div>
        <p className="mt-2 text-xs">
          Зафиксировано 3 инцидента за неделю. Рекомендуется обновить оценки
          риска по рабочим местам.
        </p>
      </div>
    </aside>
  );
};
