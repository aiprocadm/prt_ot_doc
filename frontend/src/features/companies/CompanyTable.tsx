import { type ColumnDef } from "@tanstack/react-table";
import { Eye, Pencil, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { CompanyFormDialog } from "@/features/companies/CompanyFormDialog";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyDto } from "@/types/dto/companies";
import { formatDate } from "@/utils/datetime";

interface CompanyTableProps {
  onSelect: (company: CompanyDto) => void;
}

export const CompanyTable = ({ onSelect }: CompanyTableProps) => {
  const { items, pagination, list, setPage, setPageSize, remove, loading } =
    useCompaniesStore();

  const columns = useMemo<ColumnDef<CompanyDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Название",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.name}</span>
            <span className="text-xs text-muted-foreground">
              ИНН {row.original.inn}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => (
          <span className="uppercase text-xs text-muted-foreground">
            {row.original.status}
          </span>
        ),
      },
      {
        accessorKey: "updated_at",
        header: "Обновлено",
        cell: ({ row }) => formatDate(row.original.updated_at),
      },
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onSelect(row.original)}
              aria-label="Открыть"
            >
              <Eye className="h-4 w-4" />
            </Button>
            <CompanyFormDialog
              trigger={
                <Button variant="ghost" size="icon" aria-label="Редактировать">
                  <Pencil className="h-4 w-4" />
                </Button>
              }
              initialData={row.original}
              onSubmitted={(updated) => onSelect(updated)}
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={async () => {
                if (window.confirm(`Удалить компанию ${row.original.name}?`)) {
                  await remove(row.original.id);
                  toast.success("Компания удалена");
                  list();
                }
              }}
              aria-label="Удалить"
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [list, onSelect, remove],
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
        list({});
      }}
      onPageSizeChange={(size) => {
        setPageSize(size);
        list({});
      }}
      caption="Компании"
    />
  );
};
