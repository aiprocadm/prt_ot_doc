import { type ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { useTasksStore } from "@/stores/tasks";
import type { TaskDto } from "@/types/dto/tasks";
import { formatDate } from "@/utils/datetime";

export const TaskTable = () => {
  const { items, pagination, list, setPage, setPageSize, loading } = useTasksStore();

  useEffect(() => {
    list();
  }, [list]);

  usePolling(() => list(), 8000, true);

  const columns = useMemo<ColumnDef<TaskDto>[]>(
    () => [
      {
        accessorKey: "kind",
        header: "Тип",
        cell: ({ row }) => row.original.kind
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => <StatusBadge status={row.original.status} />
      },
      {
        accessorKey: "progress",
        header: "Прогресс",
        cell: ({ row }) => `${row.original.progress}%`
      },
      {
        accessorKey: "updated_at",
        header: "Обновлено",
        cell: ({ row }) => formatDate(row.original.updated_at)
      }
    ],
    []
  );

  return (
    <DataTable
      columns={columns}
      data={items}
      isLoading={loading}
      pageIndex={pagination.page}
      pageSize={pagination.page_size}
      total={pagination.total}
      onPageChange={(page) => {
        setPage(page);
        list();
      }}
      onPageSizeChange={(size) => {
        setPageSize(size);
        list();
      }}
      caption="Задачи генерации"
    />
  );
};
