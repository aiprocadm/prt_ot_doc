import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";

import { type CompanyDto, operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

const riskLabel = (company: CompanyDto) => {
  if (company.is_hazardous_production_facility || company.has_dangerous_objects) return "Высокий";
  if ((company.hazardous_factors?.length ?? 0) > 0) return "Средний";
  return "Низкий";
};

const ContractorsPage = () => {
  const load = useCallback(() => operationsApi.getContractorSnapshot(), []);
  const { data, loading, error, reload } = useAsyncResource({ loader: load, initialData: { companies: [], sites: [], contracts: [] }, errorMessage: "Не удалось загрузить реестр подрядчиков" });

  const items = useMemo(
    () =>
      data.companies.map((company) => {
        const siteCount = data.sites.filter((site) => site.company_id === company.id).length;
        const contractCount = data.contracts.filter((contract) => contract.company_id === company.id).length;
        return { ...company, siteCount, contractCount, risk: riskLabel(company) };
      }),
    [data]
  );

  const registry = useLocalRegistry({
    items,
    match: (item, query) => [item.name, item.activity_type, item.contact_person, item.risk].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Контрагенты и подрядчики"
        description="Страница переведена с витрины на реальные tenant-aware данные из `/companies`, `/sites` и `/contracts`."
        actions={<Button asChild><Link to="/companies">Открыть компании</Link></Button>}
        stats={[
          { label: "Контрагентов", value: items.length },
          { label: "Объектов", value: data.sites.length },
          { label: "Договоров", value: data.contracts.length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка подрядчиков" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Подрядчики не найдены" description="Измените поиск или добавьте компании в tenant." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "name", header: "Контрагент" },
            { accessorKey: "activity_type", header: "Профиль", cell: ({ row }) => row.original.activity_type || "—" },
            { accessorKey: "risk", header: "Риск" },
            { accessorKey: "siteCount", header: "Объекты", cell: ({ row }) => `${row.original.siteCount} шт.` },
            { accessorKey: "contractCount", header: "Договоры", cell: ({ row }) => `${row.original.contractCount} шт.` },
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
