import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { usePacksStore } from "@/stores/packs";
import type { PackDto } from "@/types/dto/packs";
import { formatDate } from "@/utils/datetime";

export const PackTable = () => {
  const { items, pagination, list, setPage, setPageSize, loading } = usePacksStore();

  const columns = useMemo<ColumnDef<PackDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Название",
        cell: ({ row }) => row.original.name
      },
      {
        accessorKey: "company.name",
        header: "Компания",
        cell: ({ row }) => row.original.company?.name ?? "—"
      },
      {
        accessorKey: "preset",
        header: "Пресет",
        cell: ({ row }) => row.original.preset
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => <StatusBadge status={row.original.status} />
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
      caption="Последние пакеты"
    />
  );
};
