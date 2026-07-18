import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

export const EmptyState = ({
  title = "Данные отсутствуют",
  description = "Попробуйте изменить фильтры",
  action
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
}) => (
  <div className="flex flex-col items-center justify-center space-y-2 py-10 text-center text-muted-foreground">
    <Inbox className="h-10 w-10" aria-hidden="true" />
    <h3 className="text-lg font-semibold text-foreground">{title}</h3>
    <p className="max-w-xs text-sm">{description}</p>
    {action ? <div className="pt-2">{action}</div> : null}
  </div>
);
