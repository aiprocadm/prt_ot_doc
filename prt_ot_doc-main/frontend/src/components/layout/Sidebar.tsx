import { ReactNode } from "react";

export const Sidebar = ({ title, children }: { title: string; children: ReactNode }) => {
  if (!children) return null;
  return (
    <aside className="hidden w-72 flex-shrink-0 border-r bg-muted/20 p-4 lg:block" aria-label={title}>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      <div className="space-y-4 text-sm text-muted-foreground">{children}</div>
    </aside>
  );
};
