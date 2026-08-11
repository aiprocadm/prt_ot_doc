import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useTenantStore } from "@/stores/tenant";

export const TenantGate = ({ children }: { children: ReactNode }) => {
  const { tenant, tenants, setTenant } = useTenantStore();

  if (!tenant) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6 py-10">
        <Card className="w-full max-w-3xl">
          <CardHeader className="space-y-2 text-center">
            <CardTitle className="text-2xl font-semibold">Выберите контур</CardTitle>
            <p className="text-sm text-muted-foreground">
              Для загрузки данных нужен активный контур и площадка. Переключение очистит локальный кэш.
            </p>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {tenants.map((option) => (
              <Button
                key={option.id}
                variant="outline"
                className="h-auto w-full flex-col items-start gap-1 px-4 py-3 text-left"
                onClick={() => setTenant(option)}
              >
                <span className="text-sm font-semibold">{option.name}</span>
                <span className="text-xs text-muted-foreground">{option.site}</span>
              </Button>
            ))}
          </CardContent>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
};
