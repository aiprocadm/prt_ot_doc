import { useCallback } from "react";

import { opsApi, type FindingDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const FindingsPage = () => {
  const loadFindings = useCallback(() => opsApi.getFindings(), []);
  const { data: items, loading, error, reload } = useAsyncResource<FindingDto[]>({
    loader: loadFindings,
    initialData: [],
    errorMessage: "Не удалось загрузить замечания"
  });

  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.id, item.title, item.status, item.severity, item.source_type, item.finding_type, item.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Замечания и нарушения"
        description="Операционный реестр по API `/findings`: серьёзность, статус, источник и единый интерфейс с поиском."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Открытые, подтверждённые и закрытые замечания</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка замечаний" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Замечаний не найдено" description={registry.query ? "Измените строку поиска." : "В текущем тенанте пока нет записей."} />
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
                  header: "Finding",
                  cell: ({ row }) => (
                    <div>
                      <div className="font-medium">{row.original.title}</div>
                      <div className="text-xs text-muted-foreground">{row.original.finding_type}</div>
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
                  accessorKey: "severity",
                  header: "Критичность",
                  cell: ({ row }) => <Badge variant={row.original.severity === "critical" ? "destructive" : "secondary"}>{row.original.severity}</Badge>
                },
                {
                  accessorKey: "status",
                  header: "Статус",
                  cell: ({ row }) => <StatusBadge status={row.original.status} />
                }
              ]}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по title, source, severity, status"
              caption="Tenant-aware findings registry"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default FindingsPage;
