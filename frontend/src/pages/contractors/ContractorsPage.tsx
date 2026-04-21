import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";

import { type ContractorRegistryDto, operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

const complianceRiskLabel = (companyId: string, incidents: Array<{ contractor_id: string; severity: string }>) => {
  const hasCritical = incidents.some((item) => item.contractor_id === companyId && ["critical", "high"].includes(item.severity));
  if (hasCritical) return "Высокий";
  const hasMedium = incidents.some((item) => item.contractor_id === companyId && item.severity === "medium");
  if (hasMedium) return "Средний";
  return "Низкий";
};

const ContractorsPage = () => {
  const load = useCallback(() => operationsApi.getContractorSnapshot(), []);
  const { data, loading, error, reload } = useAsyncResource({ loader: load, initialData: { companies: [], sites: [], contracts: [], employees: [], incidents: [], complianceSummary: null }, errorMessage: "Не удалось загрузить реестр подрядчиков" });
  const items = useMemo(
    () =>
      data.companies.map((company: ContractorRegistryDto) => {
        const employeeCount = data.employees.filter((employee) => employee.contractor_id === company.id).length;
        const incidentCount = data.incidents.filter((incident) => incident.contractor_id === company.id).length;
        return { ...company, employeeCount, incidentCount, risk: complianceRiskLabel(company.id, data.incidents) };
      }),
    [data.companies, data.employees, data.incidents]
  );

  const registry = useLocalRegistry({
    items,
    match: (item, query) => [item.name, item.status, item.contact_person, item.risk].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Контрагенты и подрядчики"
        description="Страница использует API реестра подрядчиков `/contractors/*` с допусками, обучениями, медосмотрами и инцидентами."
        actions={<Button asChild><Link to="/companies">Открыть компании</Link></Button>}
        stats={[
          { label: "Контрагентов", value: items.length },
          { label: "Сотрудников", value: data.employees.length },
          { label: "Инцидентов", value: data.incidents.length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка подрядчиков" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Подрядчики не найдены" description="Измените поиск или добавьте компании в тенанте." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "name", header: "Контрагент" },
            { accessorKey: "status", header: "Статус", cell: ({ row }) => row.original.status || "—" },
            { accessorKey: "risk", header: "Риск" },
            { accessorKey: "employeeCount", header: "Сотрудники", cell: ({ row }) => `${row.original.employeeCount} чел.` },
            { accessorKey: "incidentCount", header: "Инциденты", cell: ({ row }) => `${row.original.incidentCount} шт.` },
            { accessorKey: "contact_person", header: "Контакт", cell: ({ row }) => row.original.contact_person || row.original.contact_phone || "—" }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по названию, профилю, контакту"
          caption="Реестр подрядчиков"
        />
      ) : null}
    </div>
  );
};

export default ContractorsPage;
