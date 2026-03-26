import { type ColumnDef } from "@tanstack/react-table";
import { Download } from "lucide-react";
import { useMemo } from "react";

import { RegistryTable } from "@/components/common/RegistryTable";
import { FilterField } from "@/components/common/FilterField";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ActionButton } from "@/components/permissions/ActionButton";
import { PERMISSIONS } from "@/permissions/permissions";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto, DocumentStatus } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

interface DocumentTableProps {
  onSelect: (document: DocumentDto) => void;
}

const STATUS_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "draft", label: "Черновик" },
  { value: "generating", label: "Генерация" },
  { value: "ready", label: "Готов" },
  { value: "error", label: "Ошибка" }
];

export const DocumentTable = ({ onSelect }: DocumentTableProps) => {
  const { items, pagination, setPage, setPageSize, list, download, loading, filters, setFilters } = useDocumentsStore();
  const safeItems = Array.isArray(items) ? items : [];
  const safePagination = pagination ?? { page: 1, page_size: 10, total: safeItems.length };

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
          <ActionButton
            permission={PERMISSIONS.DOCUMENT_EXPORT}
            abilityResource={{ status: row.original.status, company_id: row.original.company?.id }}
            variant="ghost"
            size="icon"
            disabledReason="Экспорт доступен после готовности документа"
            onClick={async () => {
              const blob = await download(row.original.id);
              downloadBlob(blob, `${row.original.name}.pdf`);
            }}
            aria-label="Скачать"
          >
            <Download className="h-4 w-4" />
          </ActionButton>
        )
      }
    ],
    [download, onSelect]
  );

  const handleSearchChange = (value: string) => {
    setFilters({ search: value || undefined });
    list({ search: value || undefined });
  };

  const handleStatusChange = (value: string) => {
    setFilters({ status: (value || undefined) as DocumentStatus | undefined });
    list({ status: (value || undefined) as DocumentStatus | undefined });
  };

  return (
    <RegistryTable
      columns={columns}
      data={safeItems}
      isLoading={loading}
      pageIndex={safePagination.page}
      pageSize={safePagination.page_size}
      total={safePagination.total}
      onPageChange={(page) => {
        setPage(page);
        list();
      }}
      onPageSizeChange={(size) => {
        setPageSize(size);
        list();
      }}
      caption="Документы"
      searchPlaceholder="Поиск по названию"
      onSearchChange={handleSearchChange}
      renderToolbar={
        <FilterField label="Статус" htmlFor="document-status">
          <select
            id="document-status"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={filters.status ?? ""}
            onChange={(event) => handleStatusChange(event.target.value)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
      }
      emptyMessage="Документы не найдены. Попробуйте изменить фильтры или поиск."
    />
  );
};
