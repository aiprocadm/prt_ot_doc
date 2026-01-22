import { AlertTriangle, FileText, ListChecks, PlayCircle, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const quickActions = [
  { label: "Создать документ", icon: FileText },
  { label: "Запустить мастер", icon: PlayCircle },
  { label: "Назначить обучение", icon: ListChecks },
  { label: "Выдать СИЗ", icon: Users }
];

const statusItems = [
  { label: "Согласования сегодня", value: "18", tone: "default" },
  { label: "Просрочки обучений", value: "7", tone: "destructive" },
  { label: "Предписания к закрытию", value: "4", tone: "secondary" }
];

export const RightDrawer = () => (
  <aside className="hidden w-72 flex-shrink-0 space-y-6 border-l bg-muted/20 p-4 xl:sticky xl:top-20 xl:block xl:self-start">
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Быстрые действия</h2>
      <div className="mt-3 space-y-2">
        {quickActions.map((action) => (
          <Button key={action.label} variant="outline" className="w-full justify-start gap-2">
            <action.icon className="h-4 w-4" />
            {action.label}
          </Button>
        ))}
      </div>
    </div>
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Сводка дня</h2>
      <div className="mt-3 space-y-2 text-sm">
        {statusItems.map((item) => (
          <div key={item.label} className="flex items-center justify-between rounded-md border bg-background px-3 py-2">
            <span>{item.label}</span>
            <Badge variant={item.tone as "default" | "secondary" | "destructive"}>{item.value}</Badge>
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-md border border-dashed bg-background p-3 text-sm text-muted-foreground">
      <div className="flex items-center gap-2 text-foreground">
        <AlertTriangle className="h-4 w-4 text-destructive" />
        Триггер пересмотра рисков
      </div>
      <p className="mt-2 text-xs">
        Зафиксировано 3 инцидента за неделю. Рекомендуется обновить оценки риска по рабочим местам.
      </p>
    </div>
  </aside>
);
