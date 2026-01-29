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
        accessorKey: "title",
        header: "Задача",
        cell: ({ row }) => row.original.title
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => <StatusBadge status={row.original.status} />
      },
      {
        accessorKey: "priority",
        header: "Приоритет",
        cell: ({ row }) => row.original.priority
      },
      {
        accessorKey: "due_at",
        header: "Срок",
        cell: ({ row }) => (row.original.due_at ? formatDate(row.original.due_at) : "—")
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
      caption="Задачи и обязательства"
    />
  );
};
