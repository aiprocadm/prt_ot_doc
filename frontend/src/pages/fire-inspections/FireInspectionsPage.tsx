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

const FireInspectionsPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getInspectionWorkspaceSnapshot(), []),
    initialData: { inspections: [], prescriptions: [], tasks: [], templates: [], packRuns: [] },
    errorMessage: "Не удалось загрузить проверки ПБ"
  });

  const registry = useLocalRegistry({ items: data.inspections, match: (item, query) => [item.authority, item.purpose, item.status, item.inspection_type].filter(Boolean).join(" ").toLowerCase().includes(query) });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пожарная безопасность · проверки и предписания"
        description="Реестр показывает реальные inspections, а также связанную нагрузку по предписаниям и задачам."
        stats={[
          { label: "Проверок", value: data.inspections.length },
          { label: "Предписаний", value: data.prescriptions.length },
          { label: "Открытых tasks", value: data.tasks.filter((item) => item.status !== "done").length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка проверок" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Проверки не найдены" description="Создайте inspections или загрузите данные." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "authority", header: "Орган" },
            { accessorKey: "inspection_type", header: "Тип" },
            { accessorKey: "purpose", header: "Цель", cell: ({ row }) => row.original.purpose || "—" },
            { accessorKey: "scheduled_at", header: "Дата", cell: ({ row }) => formatDate(row.original.scheduled_at) },
            { accessorKey: "status", header: "Статус", cell: ({ row }) => <StatusBadge status={row.original.status} /> }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по органу, цели, типу"
          caption="Проверки пожарной безопасности"
        />
      ) : null}
    </div>
  );
};

export default FireInspectionsPage;
