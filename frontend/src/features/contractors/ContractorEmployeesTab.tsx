import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ContractorEmployeeFormDialog } from "@/features/contractors/ContractorEmployeeFormDialog";
import { EmployeeAdmissionDialog } from "@/features/contractors/EmployeeAdmissionDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { COMPLIANCE_STATUS_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  ComplianceStatus,
  ContractorEmployee,
} from "@/types/dto/contractors";

const statusBadgeVariant = (
  s: ComplianceStatus,
): "default" | "secondary" | "destructive" =>
  s === "valid"
    ? "default"
    : s === "blocked" || s === "expired"
      ? "destructive"
      : "secondary";

const StatusCell = ({ value }: { value: ComplianceStatus }) => (
  <Badge variant={statusBadgeVariant(value)}>
    {COMPLIANCE_STATUS_LABELS[value] ?? value}
  </Badge>
);

export const ContractorEmployeesTab = ({
  contractorId,
  onChanged,
}: {
  contractorId: string;
  onChanged?: () => void;
}) => {
  const loader = useCallback(
    () =>
      contractorsApi
        .listEmployees({ contractor_id: contractorId })
        .then((p) => p.items),
    [contractorId],
  );
  const { data, loading, error, reload } = useAsyncResource<
    ContractorEmployee[]
  >({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить сотрудников",
  });

  const refresh = () => {
    void reload();
    onChanged?.();
  };

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) =>
      [item.full_name, item.position]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const columns: ColumnDef<ContractorEmployee, unknown>[] = [
    { accessorKey: "full_name", header: "ФИО" },
    {
      accessorKey: "position",
      header: "Должность",
      cell: ({ row }) => row.original.position || "—",
    },
    {
      accessorKey: "access_status",
      header: "Допуск",
      cell: ({ row }) => <StatusCell value={row.original.access_status} />,
    },
    {
      accessorKey: "training_status",
      header: "Обучение",
      cell: ({ row }) => <StatusCell value={row.original.training_status} />,
    },
    {
      accessorKey: "medical_status",
      header: "Медосмотр",
      cell: ({ row }) => <StatusCell value={row.original.medical_status} />,
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
            <ContractorEmployeeFormDialog
              trigger={
                <Button variant="ghost" size="sm">
                  Изменить
                </Button>
              }
              contractorId={contractorId}
              initialData={row.original}
              onSubmitted={refresh}
            />
            <EmployeeAdmissionDialog
              employee={row.original}
              trigger={
                <Button variant="ghost" size="sm">
                  Допуск
                </Button>
              }
              onAdmitted={refresh}
            />
          </div>
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorEmployeeFormDialog
            trigger={<Button>Добавить сотрудника</Button>}
            contractorId={contractorId}
            onSubmitted={refresh}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка сотрудников" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Сотрудников нет"
          description="Добавьте сотрудника подрядчика."
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
          searchPlaceholder="Поиск по ФИО, должности"
          caption="Сотрудники подрядчика"
        />
      ) : null}
    </div>
  );
};
