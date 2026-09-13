import { useCallback, useMemo } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { deniedNotice } from "@/api/partial";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const ActivitiesPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getActivitiesSnapshot(), []),
    initialData: { denied: [], tasks: [], correctiveActions: [] },
    errorMessage: "Не удалось загрузить мероприятия",
  });

  const items = useMemo(
    () =>
      data.correctiveActions.map((item) => ({
        ...item,
        task: data.tasks.find(
          (task) =>
            task.entity_id === item.id || task.entity_id === item.source_id,
        ),
      })),
    [data],
  );
  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.title, item.status, item.source_type, item.action_type]
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Мероприятия / CAPA"
        description="Страница переведена на живые данные корректирующих действий и связанных задач вместо захардкоженного массива."
        stats={[
          { label: "Действий", value: data.correctiveActions.length },
          {
            label: "Открытых задач",
            value: data.tasks.filter((task) => task.status !== "done").length,
          },
          {
            label: "Просрочено",
            value: data.tasks.filter((task) => task.overdue).length,
          },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {deniedNotice(data.denied) ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50">
          {deniedNotice(data.denied)}
        </p>
      ) : null}
      {loading ? <LoadingScreen label="Загрузка мероприятий" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Мероприятия не найдены"
          description="В тенанте ещё нет корректирующих действий."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "title", header: "Мероприятие" },
            { accessorKey: "source_type", header: "Источник" },
            { accessorKey: "action_type", header: "Тип" },
            {
              accessorKey: "due_date",
              header: "Срок",
              cell: ({ row }) => formatDate(row.original.due_date),
            },
            {
              accessorKey: "status",
              header: "Статус",
              cell: ({ row }) => <StatusBadge status={row.original.status} />,
            },
            {
              id: "task",
              header: "Связанная задача",
              cell: ({ row }) => row.original.task?.title || "—",
            },
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по мероприятию, типу, источнику"
          caption="Реестр мероприятий"
        />
      ) : null}
    </div>
  );
};

export default ActivitiesPage;
