import { useCallback } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const InspectionPlansPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      () => operationsApi.getInspectionWorkspaceSnapshot(),
      [],
    ),
    initialData: {
      inspections: [],
      prescriptions: [],
      tasks: [],
      templates: [],
      packRuns: [],
    },
    errorMessage: "Не удалось загрузить планы проверок",
  });

  const registry = useLocalRegistry({
    items: data.inspections,
    match: (item, query) =>
      [item.authority, item.status, item.purpose]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });
  const overduePlanned = data.inspections.filter(
    (item) =>
      item.status !== "done" &&
      item.status !== "closed" &&
      Boolean(
        item.scheduled_at && new Date(item.scheduled_at).getTime() < Date.now(),
      ),
  ).length;
  const openPlanTasks = data.tasks.filter(
    (item) => item.status !== "done",
  ).length;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Планы проверок"
        description="Реестр предстоящих и активных проверок с фильтрацией и постраничной навигацией."
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка планов проверок" /> : null}
      {!loading && !error && (overduePlanned > 0 || openPlanTasks > 0) ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">
              Блокеры и дальнейшие действия
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>
              Просроченных плановых проверок: {overduePlanned}. Открытых задач
              по планам: {openPlanTasks}.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to="/tasks?type=inspection">Открыть задачи</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/inspections">Открыть реестр проверок</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Планов нет"
          description="Создайте записи проверок для отображения плана."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "authority", header: "Орган" },
            {
              accessorKey: "purpose",
              header: "Цель",
              cell: ({ row }) => row.original.purpose || "—",
            },
            {
              accessorKey: "scheduled_at",
              header: "Плановая дата",
              cell: ({ row }) => formatDate(row.original.scheduled_at),
            },
            {
              accessorKey: "status",
              header: "Статус",
              cell: ({ row }) => <StatusBadge status={row.original.status} />,
            },
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
