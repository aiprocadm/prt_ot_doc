import { type ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { useTasksStore } from "@/stores/tasks";
import type { TaskDto } from "@/types/dto/tasks";
import { formatDate } from "@/utils/datetime";

const TYPE_LABELS: Record<string, string> = {
  training_plan: "Обучение",
  medical_requirement: "Медосмотры",
  inspection: "Инспекции",
  attestation: "Аттестации"
};

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
        accessorKey: "entity_type",
        header: "Тип",
        cell: ({ row }) => TYPE_LABELS[row.original.entity_type ?? ""] ?? row.original.entity_type ?? "—"
      },
      {
        accessorKey: "priority",
        header: "Приоритет",
        cell: ({ row }) => row.original.priority
      },
      {
        accessorKey: "due_at",
        header: "Срок",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span>{row.original.due_at ? formatDate(row.original.due_at) : "—"}</span>
            {row.original.overdue && <span className="text-xs text-destructive">Просрочено</span>}
          </div>
        )
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
