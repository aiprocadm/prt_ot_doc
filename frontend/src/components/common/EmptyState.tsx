import { Inbox } from "lucide-react";

export const EmptyState = ({ title = "Данные отсутствуют", description = "Попробуйте изменить фильтры" }: { title?: string; description?: string }) => (
  <div className="flex flex-col items-center justify-center space-y-2 py-10 text-center text-muted-foreground">
    <Inbox className="h-10 w-10" aria-hidden="true" />
    <h3 className="text-lg font-semibold text-foreground">{title}</h3>
    <p className="max-w-xs text-sm">{description}</p>
  </div>
);
