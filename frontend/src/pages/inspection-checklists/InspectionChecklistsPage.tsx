import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    data.prescriptions.forEach(() => {
      const current = grouped.get("general") ?? { code: "general", inspections: 0, prescriptions: 0 };
      current.prescriptions += 1;
      grouped.set("general", current);
    });
    return [...grouped.values()];
  }, [data]);

  const registry = useLocalRegistry({ items, match: (item, query) => item.code.toLowerCase().includes(query) });
  const openPrescriptions = data.prescriptions.filter((item) => item.status !== "closed").length;
  const hasChecklistGap = data.templates.length === 0 || openPrescriptions > 0;

  return (
    <div className="space-y-4">
      <RegistryPageHeader title="Чек-листы проверок" description="Экран больше не пустой: он показывает фактическое использование типов проверок как основу для чек-листового реестра." />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка чек-листов" /> : null}
      {!loading && !error && hasChecklistGap ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">Блокеры и дальнейшие действия</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>Открытых предписаний: {openPrescriptions}. Шаблонов документов для покрытия чек-листов: {data.templates.length}.</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline"><Link to="/templates">Шаблоны</Link></Button>
              <Button asChild size="sm" variant="outline"><Link to="/inspections">Проверки</Link></Button>
              <Button asChild size="sm" variant="outline"><Link to="/prescriptions">Предписания</Link></Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Чек-листы не найдены" description="В тенанте ещё не было проверок." /> : null}
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
