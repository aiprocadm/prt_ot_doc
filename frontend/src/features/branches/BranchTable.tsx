import { type ColumnDef } from "@tanstack/react-table";
import { Pencil, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { BranchFormDialog } from "@/features/branches/BranchFormDialog";
import { useBranchesStore } from "@/stores/branches";
import type { BranchDto } from "@/types/dto/branches";
import type { CompanyDto } from "@/types/dto/companies";

interface BranchTableProps {
  companies: CompanyDto[];
  canManage: boolean;
}

export const BranchTable = ({ companies, canManage }: BranchTableProps) => {
  const { items, pagination, list, setPage, setPageSize, remove, loading } = useBranchesStore();

  const companyName = useMemo(() => {
    const map = new Map(companies.map((c) => [c.id, c.name]));
    return (id: string) => map.get(id) ?? id;
  }, [companies]);

  const columns = useMemo<ColumnDef<BranchDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Филиал",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.name}</span>
            {row.original.code ? (
              <span className="text-xs text-muted-foreground">Код: {row.original.code}</span>
            ) : null}
          </div>
        )
      },
      {
        accessorKey: "company_id",
        header: "Компания",
        cell: ({ row }) => <span>{companyName(row.original.company_id)}</span>
      },
      {
        accessorKey: "contact_name",
        header: "Контакт",
        cell: ({ row }) => (
          <div className="flex flex-col text-sm">
            <span>{row.original.contact_name ?? "—"}</span>
            {row.original.contact_phone ? (
              <span className="text-xs text-muted-foreground">{row.original.contact_phone}</span>
            ) : null}
          </div>
        )
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => (
          <span className="uppercase text-xs text-muted-foreground">{row.original.status}</span>
        )
      },
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <BranchFormDialog
              companies={companies}
              initialData={row.original}
              trigger={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Редактировать"
                  disabled={!canManage}
                  title={!canManage ? "Недостаточно прав" : undefined}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
              }
            />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Удалить"
              disabled={!canManage}
              title={!canManage ? "Недостаточно прав" : undefined}
              onClick={async () => {
                if (window.confirm(`Удалить филиал ${row.original.name}?`)) {
                  await remove(row.original.id);
                  toast.success("Филиал удалён");
                }
              }}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        )
      }
    ],
    [companies, companyName, canManage, remove]
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
      caption="Филиалы"
    />
  );
};
