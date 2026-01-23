import { type ColumnDef } from "@tanstack/react-table";
import { Download } from "lucide-react";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

interface DocumentTableProps {
  onSelect: (document: DocumentDto) => void;
}

export const DocumentTable = ({ onSelect }: DocumentTableProps) => {
  const { items, pagination, setPage, setPageSize, list, download, loading } = useDocumentsStore();

  const columns = useMemo<ColumnDef<DocumentDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Документ",
        cell: ({ row }) => (
          <button type="button" className="font-medium text-primary hover:underline" onClick={() => onSelect(row.original)}>
            {row.original.name}
          </button>
        )
      },
      {
        accessorKey: "company.name",
        header: "Компания",
        cell: ({ row }) => row.original.company?.name
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => <StatusBadge status={row.original.status} />
      },
      {
        accessorKey: "version",
        header: "Версия",
        cell: ({ row }) => row.original.version
      },
      {
        accessorKey: "updated_at",
        header: "Обновлено",
        cell: ({ row }) => formatDate(row.original.updated_at)
      },
      {
        id: "download",
        header: "Скачать",
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            onClick={async () => {
              const blob = await download(row.original.id);
              downloadBlob(blob, `${row.original.name}.pdf`);
            }}
            aria-label="Скачать"
          >
            <Download className="h-4 w-4" />
          </Button>
        )
      }
    ],
    [download, onSelect]
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
      caption="Документы"
    />
  );
};
