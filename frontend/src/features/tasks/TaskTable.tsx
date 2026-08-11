import { type ColumnDef } from "@tanstack/react-table";
import { CheckCheck } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { usePolling } from "@/hooks/usePolling";

import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ActionButton } from "@/components/permissions/ActionButton";
import { PERMISSIONS } from "@/permissions/permissions";
import { useTasksStore } from "@/stores/tasks";
import type { TaskDto } from "@/types/dto/tasks";
import { formatDate } from "@/utils/datetime";
import { entityContextPath } from "@/utils/workspaceNavigation";

const TYPE_LABELS: Record<string, string> = {
  training_plan: "Обучение",
  medical_requirement: "Медосмотры",
  inspection: "Инспекции",
  attestation: "Аттестации",
  person: "Сотрудник",
  company: "Организация",
  task: "Задача"
};

export const TaskTable = () => {
  const { items, pagination, list, setPage, setPageSize, loading, patchTask } = useTasksStore();

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
        cell: ({ row }) => {
          const rawType = row.original.entity_type ?? "";
          const label = (TYPE_LABELS[rawType] ?? rawType) || "—";
          const contextHref = entityContextPath(rawType);
          if (!contextHref) {
            return label;
          }
          return (
            <Link to={contextHref} className="text-blue-600 hover:underline">
              {label}
            </Link>
          );
        }
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
        id: "actions",
        header: "Действия",
        cell: ({ row }) => (
          <ActionButton
            permission={PERMISSIONS.TASK_UPDATE}
            variant="ghost"
            size="icon"
            title="Закрыть"
            onClick={() => patchTask(row.original.id, { status: "done" })}
          >
            <CheckCheck className="h-4 w-4" />
          </ActionButton>
        )
      }
    ],
    [patchTask]
  );

  return (
    <RegistryTable
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
