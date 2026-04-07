import { useCallback } from "react";

import { opsApi, type PrescriptionDto } from "@/api/ops";
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

const PrescriptionsPage = () => {
  const loadPrescriptions = useCallback(() => opsApi.getPrescriptions(), []);
  const { data: items, loading, error, reload } = useAsyncResource<PrescriptionDto[]>({
    loader: loadPrescriptions,
    initialData: [],
    errorMessage: "Не удалось загрузить предписания"
  });

  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.id, item.description, item.status, item.inspection_id, item.incident_id]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Предписания"
        description="Операционный реестр предписаний из backend `/prescriptions` с фильтрацией по тенанту, поиском и постраничной навигацией."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Открытые и закрытые предписания</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка предписаний" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Предписания не найдены" description={registry.query ? "Измените запрос поиска." : "В этом tenant пока нет предписаний."} />
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
                  accessorKey: "description",
                  header: "Описание"
                },
                {
                  id: "source",
                  header: "Источник",
                  cell: ({ row }) =>
                    row.original.incident_id
                      ? `Incident ${row.original.incident_id.slice(0, 8)}`
                      : `Inspection ${row.original.inspection_id.slice(0, 8)}`
                },
                {
                  accessorKey: "due_at",
                  header: "Срок",
                  cell: ({ row }) => formatDate(row.original.due_at) || "—"
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
              searchPlaceholder="Поиск по описанию, inspection_id, incident_id"
              caption="Реестр tenant-scoped предписаний"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PrescriptionsPage;
