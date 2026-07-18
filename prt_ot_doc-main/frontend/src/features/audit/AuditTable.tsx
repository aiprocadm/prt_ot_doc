import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { useAuditStore } from "@/stores/audit";
import type { AuditLogDto } from "@/types/dto/audit";
import { formatDate } from "@/utils/datetime";

export const AuditTable = () => {
  const { items, pagination, setPage, setPageSize, list, loading } = useAuditStore();

  const columns = useMemo<ColumnDef<AuditLogDto>[]>(
    () => [
      {
        accessorKey: "actor.full_name",
        header: "Пользователь",
        cell: ({ row }) => row.original.actor.full_name
      },
      {
        accessorKey: "action",
        header: "Действие",
        cell: ({ row }) => row.original.action
      },
      {
        accessorKey: "entity_type",
        header: "Объект",
        cell: ({ row }) => row.original.entity_type
      },
      {
        accessorKey: "created_at",
        header: "Время",
        cell: ({ row }) => formatDate(row.original.created_at)
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
      caption="Журнал действий"
    />
  );
};
