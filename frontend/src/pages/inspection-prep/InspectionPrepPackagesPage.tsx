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

const InspectionPrepPackagesPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getInspectionWorkspaceSnapshot(), []),
    initialData: { inspections: [], prescriptions: [], tasks: [], templates: [], packRuns: [] },
    errorMessage: "Не удалось загрузить пакеты подготовки"
  });

  const items = useMemo(() => data.inspections.map((inspection) => ({
    id: inspection.id,
    authority: inspection.authority,
    status: inspection.status,
    blockers: data.prescriptions.filter((item) => item.inspection_id === inspection.id && item.status !== "closed").length,
    openTasks: data.tasks.filter((item) => item.entity_id === inspection.id && item.status !== "done").length,
    templateCoverage: data.templates.length
  })), [data]);
  const registry = useLocalRegistry({ items, match: (item, query) => [item.authority, item.status].join(" ").toLowerCase().includes(query) });
  const totalBlockers = items.reduce((sum, item) => sum + item.blockers, 0);
  const totalOpenTasks = items.reduce((sum, item) => sum + item.openTasks, 0);

  return (
    <div className="space-y-4">
      <RegistryPageHeader title="Пакеты подготовки к проверке" description="Foundation-level but real projection из inspections, prescriptions, tasks и template coverage вместо статического текста." />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка пакетов подготовки" /> : null}
      {!loading && !error && (totalBlockers > 0 || totalOpenTasks > 0) ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">Blockers и next actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>Открытых blockers по предписаниям: {totalBlockers}. Открытых задач подготовки: {totalOpenTasks}.</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline"><Link to="/prescriptions">Предписания</Link></Button>
              <Button asChild size="sm" variant="outline"><Link to="/tasks?type=inspection">Задачи подготовки</Link></Button>
              <Button asChild size="sm" variant="outline"><Link to="/templates">Покрытие шаблонами</Link></Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Пакеты подготовки не сформированы" description="Нет inspections для подготовки." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "authority", header: "Орган" },
            { accessorKey: "status", header: "Статус проверки" },
            { accessorKey: "blockers", header: "Blockers" },
            { accessorKey: "openTasks", header: "Открытые задачи" },
            { accessorKey: "templateCoverage", header: "Template coverage" }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по органу и статусу"
          caption="Inspection prep packages"
        />
      ) : null}
    </div>
  );
};

export default InspectionPrepPackagesPage;
