import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { usePersonsStore } from "@/stores/persons";
import type { PersonDto } from "@/types/dto/persons";
import { formatDate } from "@/utils/datetime";

interface PersonTableProps {
  onSelect: (person: PersonDto) => void;
}

export const PersonTable = ({ onSelect }: PersonTableProps) => {
  const { items, pagination, setPage, setPageSize, list, loading } = usePersonsStore();

  const columns = useMemo<ColumnDef<PersonDto>[]>(
    () => [
      {
        accessorKey: "full_name",
        header: "ФИО",
        cell: ({ row }) => (
          <button
            type="button"
            className="text-left font-medium text-primary hover:underline"
            onClick={() => onSelect(row.original)}
          >
            {row.original.full_name}
          </button>
        )
      },
      {
        accessorKey: "position",
        header: "Должность",
        cell: ({ row }) => row.original.position ?? "—"
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
    [onSelect]
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
      caption="Сотрудники"
    />
  );
};
