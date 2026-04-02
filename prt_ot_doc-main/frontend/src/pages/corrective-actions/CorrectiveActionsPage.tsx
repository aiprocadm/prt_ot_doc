import { useCallback } from "react";

import { opsApi, type CorrectiveActionDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const CorrectiveActionsPage = () => {
  const loadActions = useCallback(() => opsApi.getCorrectiveActions(), []);
  const { data: items, loading, error, reload } = useAsyncResource<CorrectiveActionDto[]>({
    loader: loadActions,
    initialData: [],
    errorMessage: "Не удалось загрузить CAPA"
  });

  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.id, item.title, item.status, item.source_type, item.action_type, item.effectiveness_status, item.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Корректирующие действия"
        description="Операционный CAPA-реестр на основе backend `/corrective-actions` с реальными due/status/effectiveness полями, единым UX и пагинацией."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Корректирующие и предупреждающие действия</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка CAPA" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Действия не найдены" description={registry.query ? "Попробуйте другой запрос." : "В текущем tenant пока нет корректирующих действий."} />
          ) : null}
          {!loading && !error && registry.total > 0 ? (
            <RegistryTable
              columns={[
                {
                  accessorKey: "id",
                  header: "ID",
                  cell: ({ row }) => <span className="font-medium">{row.original.id.slice(0, 8)}</span>
                },
                {
                  accessorKey: "title",
                  header: "Мероприятие",
                  cell: ({ row }) => (
                    <div>
                      <div className="font-medium">{row.original.title}</div>
                      <div className="text-xs text-muted-foreground">{row.original.action_type}</div>
                    </div>
                  )
                },
                {
                  id: "source",
                  header: "Источник",
                  cell: ({ row }) => (
                    <div>
                      <div>{row.original.source_type}</div>
                      <div className="text-xs text-muted-foreground">{row.original.source_id.slice(0, 8)}</div>
                    </div>
                  )
                },
                {
                  accessorKey: "due_date",
                  header: "Срок",
                  cell: ({ row }) => formatDate(row.original.due_date) || "—"
                },
                {
                  accessorKey: "status",
                  header: "Статус",
                  cell: ({ row }) => <StatusBadge status={row.original.status} />
                },
                {
                  accessorKey: "effectiveness_status",
                  header: "Эффективность",
                  cell: ({ row }) => row.original.effectiveness_status ?? "—"
                }
              ]}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по мероприятию, source, status"
              caption="CAPA registry with tenant-aware live data"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CorrectiveActionsPage;
