import { useEffect, useState } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuditStore } from "@/stores/audit";
import { AuditTable } from "@/features/audit/AuditTable";
import { ROUTES } from "@/router/routes";

const AuditPage = () => {
  const { setFilters, list, filters, items, loading, error } = useAuditStore();
  const [search, setSearch] = useState(filters.search ?? "");

  useEffect(() => {
    list();
  }, [list]);

  const applyFilters = () => {
    setFilters({ search: search || undefined });
    list();
  };

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[{ label: "Главная", to: ROUTES.DASHBOARD }, { label: "Аудит" }]}
      />
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-6">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="audit-search">
              Поиск
            </label>
            <Input
              id="audit-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Button onClick={applyFilters}>Применить</Button>
        </CardContent>
      </Card>
      <ErrorState error={error ?? undefined} onRetry={() => void list()} />
      {loading ? <LoadingScreen label="Загрузка журнала аудита" /> : null}
      {!loading && !error && items.length === 0 ? (
        <EmptyState
          title="События аудита не найдены"
          description="Измените фильтры или выполните действия в системе, чтобы сформировать журнал."
        />
      ) : null}
      {!loading && !error && items.length > 0 ? <AuditTable /> : null}
    </div>
  );
};

export default AuditPage;
