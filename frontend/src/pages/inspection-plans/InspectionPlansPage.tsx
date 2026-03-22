import { useCallback } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const InspectionPlansPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getInspectionWorkspaceSnapshot(), []),
    initialData: { inspections: [], prescriptions: [], tasks: [], templates: [], packRuns: [] },
    errorMessage: "Не удалось загрузить планы проверок"
  });

  const registry = useLocalRegistry({ items: data.inspections, match: (item, query) => [item.authority, item.status, item.purpose].filter(Boolean).join(" ").toLowerCase().includes(query) });

  return (
    <div className="space-y-4">
      <RegistryPageHeader title="Планы проверок" description="Реальный registry upcoming/active inspections с фильтрацией и постраничной навигацией." />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка планов проверок" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Планов нет" description="Создайте inspection records для отображения плана." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "authority", header: "Орган" },
            { accessorKey: "purpose", header: "Цель", cell: ({ row }) => row.original.purpose || "—" },
            { accessorKey: "scheduled_at", header: "Плановая дата", cell: ({ row }) => formatDate(row.original.scheduled_at) },
            { accessorKey: "status", header: "Статус", cell: ({ row }) => <StatusBadge status={row.original.status} /> }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по органу, цели, статусу"
          caption="Планы проверок"
        />
      ) : null}
    </div>
  );
};

export default InspectionPlansPage;
