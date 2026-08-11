import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { useNpaStore } from "@/stores/npa";
import type { NpaDto } from "@/types/dto/npa";
import { formatDate } from "@/utils/datetime";

export const NpaTable = () => {
  const { items, pagination, setPage, setPageSize, list, loading } =
    useNpaStore();

  const columns = useMemo<ColumnDef<NpaDto>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Документ",
        cell: ({ row }) => (
          <a
            href={row.original.link ?? "#"}
            className="text-primary hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            {row.original.title}
          </a>
        ),
      },
      {
        accessorKey: "code",
        header: "Номер",
        cell: ({ row }) => row.original.code ?? "—",
      },
      {
        accessorKey: "issuer",
        header: "Орган",
        cell: ({ row }) => row.original.issuer ?? "—",
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => row.original.status,
      },
      {
        accessorKey: "effective_at",
        header: "Актуально на",
        cell: ({ row }) => formatDate(row.original.effective_at),
      },
    ],
    [],
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
      caption="Реестр НПА"
    />
  );
};
