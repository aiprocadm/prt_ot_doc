import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";

interface RegistryStat {
  label: string;
  value: ReactNode;
  hint?: string;
}

interface RegistryPageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  stats?: RegistryStat[];
}

export const RegistryPageHeader = ({
  title,
  description,
  actions,
  stats,
}: RegistryPageHeaderProps) => (
  <Card>
    <CardContent className="flex flex-col gap-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
      {stats && stats.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-lg border border-border bg-background p-4 shadow-sm"
            >
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {stat.label}
              </p>
              <p className="mt-2 text-2xl font-semibold text-foreground">
                {stat.value}
              </p>
              {stat.hint && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {stat.hint}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </CardContent>
  </Card>
);
