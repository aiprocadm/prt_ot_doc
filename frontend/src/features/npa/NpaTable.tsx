import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { useNpaStore } from "@/stores/npa";
import type { NpaDto } from "@/types/dto/npa";

/** Дата акта без времени: у `valid_from`/`valid_to` его нет. */
const formatDay = (value?: string | null): string => {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return day && month && year ? `${day}.${month}.${year}` : value;
};

/**
 * «Действует / утратил силу» по датам — статуса как поля у акта нет.
 * Срок считаем по календарю пользователя: реестр справочный, а не расчётный.
 */
export const npaValidity = (
  item: Pick<NpaDto, "valid_from" | "valid_to">,
  today = new Date().toISOString().slice(0, 10),
): "действует" | "утратил силу" | "ещё не вступил" => {
  if (item.valid_to && item.valid_to < today) return "утратил силу";
  if (item.valid_from && item.valid_from > today) return "ещё не вступил";
  return "действует";
};

export const NpaTable = () => {
  const { items, pagination, setPage, setPageSize, loading } = useNpaStore();

  const columns = useMemo<ColumnDef<NpaDto>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Документ",
        cell: ({ row }) => row.original.title,
      },
      {
        accessorKey: "code",
        header: "Номер",
        cell: ({ row }) => row.original.code,
      },
      {
        accessorKey: "edition",
        header: "Редакция",
        cell: ({ row }) => row.original.edition,
      },
      {
        accessorKey: "valid_from",
        header: "Действует с",
        cell: ({ row }) => formatDay(row.original.valid_from),
      },
      {
        id: "validity",
        header: "Актуальность",
        cell: ({ row }) => npaValidity(row.original),
      },
      {
        // Срез-201: в одном списке лежат федеральные акты и собственные приказы
        // организации. Это не украшение: править можно только свои, и без
        // колонки человек узнавал бы об этом отказом.
        id: "scope",
        header: "Чей акт",
        cell: ({ row }) => (
          <span data-testid="npa-scope" data-scope={row.original.scope}>
            {row.original.scope_title ?? "—"}
          </span>
        ),
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
      onPageChange={setPage}
      onPageSizeChange={setPageSize}
      caption="Реестр НПА"
    />
  );
};
