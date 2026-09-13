import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { deniedNotice } from "@/api/partial";
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
    loader: useCallback(
      () => operationsApi.getInspectionWorkspaceSnapshot(),
      [],
    ),
    initialData: {
      denied: [],
      inspections: [],
      prescriptions: [],
      tasks: [],
      templates: [],
      packRuns: [],
    },
    errorMessage: "Не удалось загрузить пакеты подготовки",
  });

  const items = useMemo(
    () =>
      data.inspections.map((inspection) => ({
        id: inspection.id,
        authority: inspection.authority,
        status: inspection.status,
        blockers: data.prescriptions.filter(
          (item) =>
            item.inspection_id === inspection.id && item.status !== "closed",
        ).length,
        openTasks: data.tasks.filter(
          (item) => item.entity_id === inspection.id && item.status !== "done",
        ).length,
        templateCoverage: data.templates.length,
      })),
    [data],
  );
  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.authority, item.status].join(" ").toLowerCase().includes(query),
  });
  const totalBlockers = items.reduce((sum, item) => sum + item.blockers, 0);
  const totalOpenTasks = items.reduce((sum, item) => sum + item.openTasks, 0);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пакеты подготовки к проверке"
        description="Реальная сводка по проверкам, предписаниям, задачам и покрытию шаблонами вместо статического текста."
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {deniedNotice(data.denied) ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50">
          {deniedNotice(data.denied)}
        </p>
      ) : null}
      {loading ? <LoadingScreen label="Загрузка пакетов подготовки" /> : null}
      {!loading && !error && (totalBlockers > 0 || totalOpenTasks > 0) ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">
              Блокеры и дальнейшие действия
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>
              Открытых ограничений по предписаниям: {totalBlockers}. Открытых
              задач подготовки: {totalOpenTasks}.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to="/prescriptions">Предписания</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/tasks?type=inspection">Задачи подготовки</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/templates">Покрытие шаблонами</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Пакеты подготовки не сформированы"
          description="Нет проверок для подготовки."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "authority", header: "Орган" },
            { accessorKey: "status", header: "Статус проверки" },
            { accessorKey: "blockers", header: "Ограничения" },
            { accessorKey: "openTasks", header: "Открытые задачи" },
            { accessorKey: "templateCoverage", header: "Покрытие шаблонами" },
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по органу и статусу"
          caption="Пакеты подготовки к проверкам"
        />
      ) : null}
    </div>
  );
};

export default InspectionPrepPackagesPage;
