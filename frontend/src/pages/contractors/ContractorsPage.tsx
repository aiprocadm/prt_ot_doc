import { useCallback, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { type ContractorComplianceSummaryDto, type ContractorRegistryDto, operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

const emptyComplianceSummary = (): ContractorComplianceSummaryDto => ({
  employees_total: 0,
  admission: {},
  training: {},
  medical: {}
});

const complianceRiskLabel = (companyId: string, incidents: Array<{ contractor_id: string; severity: string }>) => {
  const hasCritical = incidents.some((item) => item.contractor_id === companyId && ["critical", "high"].includes(item.severity));
  if (hasCritical) return "Высокий";
  const hasMedium = incidents.some((item) => item.contractor_id === companyId && item.severity === "medium");
  if (hasMedium) return "Средний";
  return "Низкий";
};

const ContractorsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const load = useCallback(() => operationsApi.getContractorSnapshot(), []);
  const { data, loading, error, reload } = useAsyncResource({
    loader: load,
    initialData: { companies: [], hostCompanies: [], sites: [], contracts: [], employees: [], incidents: [], complianceSummary: emptyComplianceSummary() },
    errorMessage: "Не удалось загрузить реестр подрядчиков"
  });
  const contractorCompanies = data.companies ?? [];
  const employees = data.employees ?? [];
  const incidents = data.incidents ?? [];
  const selectedCompanyId = searchParams.get("company_id") ?? "";
  const hostCompanyById = useMemo(() => new Map((data.hostCompanies ?? []).map((company) => [company.id, company.name])), [data.hostCompanies]);
  const items = useMemo(
    () =>
      contractorCompanies.map((company: ContractorRegistryDto) => {
        const employeeCount = employees.filter((employee) => employee.contractor_id === company.id).length;
        const incidentCount = incidents.filter((incident) => incident.contractor_id === company.id).length;
        const hostCompanyName = company.company_id ? (hostCompanyById.get(company.company_id) ?? company.company_id) : "Не привязан";
        return { ...company, employeeCount, incidentCount, risk: complianceRiskLabel(company.id, incidents), hostCompanyName };
      }),
    [contractorCompanies, employees, incidents, hostCompanyById]
  );
  const filteredItems = useMemo(
    () => (selectedCompanyId ? items.filter((item) => item.company_id === selectedCompanyId) : items),
    [items, selectedCompanyId]
  );

  const registry = useLocalRegistry({
    items: filteredItems,
    match: (item, query) =>
      [item.name, item.status, item.contact_person, item.risk, item.hostCompanyName].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Контрагенты и подрядчики"
        description="Страница использует API реестра подрядчиков `/contractors/*` с допусками, обучениями, медосмотрами и инцидентами."
        actions={<Button asChild><Link to="/companies">Открыть компании</Link></Button>}
        stats={[
          { label: "Контрагентов", value: items.length },
          { label: "Привязано к компаниям", value: items.filter((item) => Boolean(item.company_id)).length },
          { label: "Сотрудников", value: employees.length },
          { label: "Инцидентов", value: incidents.length }
        ]}
      />
      <div className="flex items-center gap-2">
        <label htmlFor="contractors-company-filter" className="text-sm text-muted-foreground">Компания:</label>
        <select
          id="contractors-company-filter"
          className="h-10 min-w-64 rounded-md border px-3"
          value={selectedCompanyId}
          onChange={(event) => {
            const next = new URLSearchParams(searchParams);
            if (event.target.value) next.set("company_id", event.target.value);
            else next.delete("company_id");
            setSearchParams(next, { replace: true });
          }}
        >
          <option value="">Все компании</option>
          {(data.hostCompanies ?? []).map((company) => (
            <option key={company.id} value={company.id}>{company.name}</option>
          ))}
        </select>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка подрядчиков" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Подрядчики не найдены"
          description={selectedCompanyId ? "Для выбранной компании подрядчики не найдены." : "Измените поиск или добавьте компании в тенанте."}
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "name", header: "Контрагент" },
            { accessorKey: "hostCompanyName", header: "Компания-заказчик" },
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
