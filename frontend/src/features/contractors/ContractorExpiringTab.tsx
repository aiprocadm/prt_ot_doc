import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Badge } from "@/components/ui/badge";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { DOC_TYPE_LABELS, EXPIRY_BADGE_VARIANT, EXPIRY_LABELS } from "@/pages/contractors/contractorsVocab";
import { formatDate } from "@/utils/datetime";
import type { ContractorDocument } from "@/types/dto/contractors";

export const ContractorExpiringTab = () => {
  const loader = useCallback(() => contractorsApi.listExpiringDocuments().then((p) => p.items), []);
  const { data, loading, error, reload } = useAsyncResource<ContractorDocument[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить истекающие документы"
  });

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.title, item.number, item.doc_type].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorDocument, unknown>[] = [
    { accessorKey: "title", header: "Документ" },
    { accessorKey: "doc_type", header: "Тип", cell: ({ row }) => DOC_TYPE_LABELS[row.original.doc_type] ?? row.original.doc_type },
    { accessorKey: "valid_until", header: "Действует до", cell: ({ row }) => formatDate(row.original.valid_until ?? "") || "—" },
    {
      accessorKey: "expiry_status",
      header: "Состояние",
      cell: ({ row }) => (
        <Badge variant={EXPIRY_BADGE_VARIANT[row.original.expiry_status]}>{EXPIRY_LABELS[row.original.expiry_status]}</Badge>
      )
    }
  ];

  if (error && isFeatureDisabledError(error)) {
    return <EmptyState title="Функция недоступна" description="Документы подрядчиков не включены для этого тенанта." />;
  }

  return (
    <div className="space-y-3">
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка документов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Нет истекающих документов" description="Все документы подрядчиков в порядке." />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по документу"
          caption="Истекающие документы подрядчиков"
        />
      ) : null}
    </div>
  );
};
