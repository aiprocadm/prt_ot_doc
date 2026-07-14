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
import { ContractorIncidentFormDialog } from "@/features/contractors/ContractorIncidentFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { SEVERITY_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import { formatDate } from "@/utils/datetime";
import type { ContractorIncident, IncidentSeverity } from "@/types/dto/contractors";

const severityVariant = (s: IncidentSeverity): "default" | "secondary" | "destructive" =>
  s === "critical" || s === "high" ? "destructive" : s === "medium" ? "secondary" : "default";

export const ContractorIncidentsTab = ({ contractorId }: { contractorId: string }) => {
  const loader = useCallback(() => contractorsApi.listIncidents({ contractor_id: contractorId }).then((p) => p.items), [contractorId]);
  const { data, loading, error, reload } = useAsyncResource<ContractorIncident[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить инциденты"
  });

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.incident_type, item.status].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorIncident, unknown>[] = [
    { accessorKey: "incident_type", header: "Тип" },
    {
      accessorKey: "severity",
      header: "Тяжесть",
      cell: ({ row }) => <Badge variant={severityVariant(row.original.severity)}>{SEVERITY_LABELS[row.original.severity]}</Badge>
    },
    { accessorKey: "status", header: "Статус", cell: ({ row }) => row.original.status || "—" },
    { accessorKey: "occurred_at", header: "Когда", cell: ({ row }) => formatDate(row.original.occurred_at) || "—" }
  ];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorIncidentFormDialog
            trigger={<Button>Зарегистрировать инцидент</Button>}
            contractorId={contractorId}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка инцидентов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Инцидентов нет" description="Инциденты по этому подрядчику не зарегистрированы." />
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
          searchPlaceholder="Поиск по типу инцидента"
          caption="Инциденты подрядчика"
        />
      ) : null}
    </div>
  );
};
