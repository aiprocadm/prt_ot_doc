import { useCallback, useMemo } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

const InspectionChecklistsPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getInspectionWorkspaceSnapshot(), []),
    initialData: { inspections: [], prescriptions: [], tasks: [], templates: [], packRuns: [] },
    errorMessage: "Не удалось загрузить чек-листы проверок"
  });

  const items = useMemo(() => {
    const grouped = new Map<string, { code: string; inspections: number; prescriptions: number }>();
    data.inspections.forEach((item) => {
      const code = item.inspection_type || "general";
      const current = grouped.get(code) ?? { code, inspections: 0, prescriptions: 0 };
      current.inspections += 1;
      grouped.set(code, current);
    });
    data.prescriptions.forEach((item) => {
      const current = grouped.get("general") ?? { code: "general", inspections: 0, prescriptions: 0 };
      current.prescriptions += 1;
      grouped.set("general", current);
    });
    return [...grouped.values()];
  }, [data]);

  const registry = useLocalRegistry({ items, match: (item, query) => item.code.toLowerCase().includes(query) });

  return (
    <div className="space-y-4">
      <RegistryPageHeader title="Чек-листы проверок" description="Экран больше не пустой: он показывает фактическое использование inspection types как foundation для чек-листового реестра." />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка чек-листов" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Чек-листы не найдены" description="В tenant еще не было проверок." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "code", header: "Код/тип" },
            { accessorKey: "inspections", header: "Проверок" },
            { accessorKey: "prescriptions", header: "Предписаний" }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по типу проверки"
          caption="Фактическое использование checklists"
        />
      ) : null}
    </div>
  );
};

export default InspectionChecklistsPage;
