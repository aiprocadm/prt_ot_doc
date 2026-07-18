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
    errorMessage: "Не удалось загрузить findings"
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
        title="Findings"
        description="Tenant-aware operational registry backed by backend `/findings`, with real severity/status/source projections, unified registry UX and pagination."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Открытые, подтверждённые и закрытые findings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка findings" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Findings не найдены" description={registry.query ? "Измените строку поиска." : "В текущем tenant пока нет findings."} />
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
