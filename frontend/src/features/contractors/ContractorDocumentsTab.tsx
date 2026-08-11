import { useCallback, useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ContractorDocumentFormDialog } from "@/features/contractors/ContractorDocumentFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import {
  DOC_TYPE_LABELS,
  DOC_TYPE_OPTIONS,
  EXPIRY_BADGE_VARIANT,
  EXPIRY_LABELS,
} from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import { formatDate } from "@/utils/datetime";
import type {
  ContractorDocument,
  ContractorEmployee,
  DocType,
} from "@/types/dto/contractors";

export const ContractorDocumentsTab = ({
  contractorId,
}: {
  contractorId: string;
}) => {
  const [docTypeFilter, setDocTypeFilter] = useState<DocType | "">("");
  const [employees, setEmployees] = useState<ContractorEmployee[]>([]);

  const loader = useCallback(
    () =>
      contractorsApi
        .listDocuments({
          contractor_id: contractorId,
          ...(docTypeFilter ? { doc_type: docTypeFilter } : {}),
        })
        .then((p) => p.items),
    [contractorId, docTypeFilter],
  );
  const { data, loading, error, reload } = useAsyncResource<
    ContractorDocument[]
  >({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить документы",
  });

  useEffect(() => {
    contractorsApi
      .listEmployees({ contractor_id: contractorId })
      .then((p) => setEmployees(p.items))
      .catch(() => undefined);
  }, [contractorId]);

  const onArchive = async (id: string) => {
    if (!window.confirm("Архивировать документ?")) return;
    try {
      await contractorsApi.archiveDocument(id);
      toast.success("Документ архивирован");
      void reload();
    } catch (err) {
      toast.error(
        (err as { message?: string })?.message ??
          "Не удалось архивировать документ",
      );
    }
  };

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) =>
      [item.title, item.number, item.issuing_org]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const columns: ColumnDef<ContractorDocument, unknown>[] = [
    { accessorKey: "title", header: "Документ" },
    {
      accessorKey: "doc_type",
      header: "Тип",
      cell: ({ row }) =>
        DOC_TYPE_LABELS[row.original.doc_type] ?? row.original.doc_type,
    },
    {
      accessorKey: "valid_until",
      header: "Действует до",
      cell: ({ row }) => formatDate(row.original.valid_until ?? "") || "—",
    },
    {
      accessorKey: "expiry_status",
      header: "Состояние",
      cell: ({ row }) => (
        <Badge variant={EXPIRY_BADGE_VARIANT[row.original.expiry_status]}>
          {EXPIRY_LABELS[row.original.expiry_status]}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => (
        <Can
          permission={PERMISSIONS.CONTRACTOR_MANAGE}
          fallback={<span className="text-muted-foreground">—</span>}
        >
          <div className="flex gap-2">
            <ContractorDocumentFormDialog
              trigger={
                <Button variant="ghost" size="sm">
                  Изменить
                </Button>
              }
              contractorId={contractorId}
              employees={employees}
              initialData={row.original}
              onSubmitted={() => void reload()}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void onArchive(row.original.id)}
            >
              Архивировать
            </Button>
          </div>
        </Can>
      ),
    },
  ];

  if (error && isFeatureDisabledError(error)) {
    return (
      <EmptyState
        title="Функция недоступна"
        description="Документы подрядчиков не включены для этого тенанта."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <select
          className="h-9 rounded-md border px-3 text-sm"
          value={docTypeFilter}
          onChange={(e) => setDocTypeFilter(e.target.value as DocType | "")}
          aria-label="Фильтр по типу документа"
        >
          <option value="">Все типы</option>
          {DOC_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {DOC_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorDocumentFormDialog
            trigger={<Button>Добавить документ</Button>}
            contractorId={contractorId}
            employees={employees}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка документов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Документов нет"
          description="Добавьте документ подрядчика."
        />
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
          caption="Документы подрядчика"
        />
      ) : null}
    </div>
  );
};
