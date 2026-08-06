import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { getDownloadUrl } from "@/api/files";
import { DataTable } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { useFilesStore } from "@/stores/files";
import type { FileDto } from "@/types/dto/files";
import { formatDate } from "@/utils/datetime";

export const FileTable = () => {
  const { items, pagination, list, setPage, setPageSize, remove, loading } =
    useFilesStore();

  const columns = useMemo<ColumnDef<FileDto>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Файл",
        cell: ({ row }) => row.original.name,
      },
      {
        accessorKey: "mime_type",
        header: "Тип",
        cell: ({ row }) => row.original.mime_type,
      },
      {
        accessorKey: "size",
        header: "Размер",
        cell: ({ row }) => `${(row.original.size / 1024).toFixed(1)} КБ`,
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) =>
          (row.original as FileDto & { status?: string }).status ?? "—",
      },
      {
        accessorKey: "created_at",
        header: "Загружен",
        cell: ({ row }) => formatDate(row.original.created_at),
      },
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }) => (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={
                (row.original as FileDto & { status?: string }).status !==
                "ready"
              }
              onClick={async () => {
                const url = await getDownloadUrl(
                  row.original.id,
                  "files_table_download",
                );
                window.open(url, "_blank", "noopener,noreferrer");
              }}
            >
              Скачать
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                if (window.confirm("Удалить файл?")) {
                  await remove(row.original.id);
                  list();
                }
              }}
            >
              Удалить
            </Button>
          </div>
        ),
      },
    ],
    [list, remove],
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
      caption="Файлы"
    />
  );
};
