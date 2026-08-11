import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";
import { formatDate } from "@/utils/datetime";

interface TemplateTableProps {
  onSelect: (template: TemplateDto) => void;
}

export const TemplateTable = ({ onSelect }: TemplateTableProps) => {
  const { items, pagination, list, setPage, setPageSize, loading } = useTemplatesStore();

  const columns = useMemo<ColumnDef<TemplateDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Название",
        cell: ({ row }) => (
          <button type="button" className="font-medium text-primary hover:underline" onClick={() => onSelect(row.original)}>
            {row.original.name}
          </button>
        )
      },
      {
        accessorKey: "template_type",
        header: "Тип",
        cell: ({ row }) => row.original.template_type ?? row.original.current_version?.document_type ?? "—"
      },
      {
        accessorKey: "current_version.status",
        header: "Статус",
        cell: ({ row }) => <StatusBadge status={row.original.current_version?.status} />
      },
      {
        accessorKey: "scope.type",
        header: "Scope",
        cell: ({ row }) => row.original.scope?.type ?? "tenant"
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
      caption="Шаблоны"
    />
  );
};
