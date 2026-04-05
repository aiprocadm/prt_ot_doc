import { useCallback, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { type CompanyDto, operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { entityCardLink } from "@/utils/workspaceNavigation";

const riskLabel = (company: CompanyDto) => {
  if (company.is_hazardous_production_facility || company.has_dangerous_objects) return "Высокий";
  if ((company.hazardous_factors?.length ?? 0) > 0) return "Средний";
  return "Низкий";
};

const ContractorsPage = () => {
  const [searchParams] = useSearchParams();
  const load = useCallback(() => operationsApi.getContractorSnapshot(), []);
  const { data, loading, error, reload } = useAsyncResource({ loader: load, initialData: { companies: [], sites: [], contracts: [] }, errorMessage: "Не удалось загрузить реестр подрядчиков" });
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;
  const focusedView = searchParams.get("view") === "timeline" ? "timeline" : "summary";

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

  const focusedCompany = useMemo(() => {
    if (!focusedEntityId || !focusedEntityType) return null;
    if (focusedEntityType === "company") return data.companies.find((company) => company.id === focusedEntityId) ?? null;
    if (focusedEntityType === "site") {
      const site = data.sites.find((item) => item.id === focusedEntityId);
      return site ? data.companies.find((company) => company.id === site.company_id) ?? null : null;
    }
    if (focusedEntityType === "contract") {
      const contract = data.contracts.find((item) => item.id === focusedEntityId);
      return contract ? data.companies.find((company) => company.id === contract.company_id) ?? null : null;
    }
    return null;
  }, [data.companies, data.contracts, data.sites, focusedEntityId, focusedEntityType]);

  const focusedContracts = useMemo(() => {
    if (!focusedCompany) return [];
    return data.contracts
      .filter((contract) => contract.company_id === focusedCompany.id)
      .sort((a, b) => (a.expires_at ?? "").localeCompare(b.expires_at ?? ""));
  }, [data.contracts, focusedCompany]);

  const focusSummaryLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "summary"),
    [focusedEntityId, focusedEntityType]
  );
  const focusTimelineLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "timeline"),
    [focusedEntityId, focusedEntityType]
  );

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
      {focusedEntityId && ["company", "site", "contract"].includes(focusedEntityType ?? "") ? (
        <div className="rounded-md border bg-muted/20 p-4" data-testid="contractor-focus-card">
          <div className="text-sm font-semibold">Фокус контрагента из рабочего пространства</div>
          <p className="mt-1 text-xs text-muted-foreground">
            {focusedCompany
              ? `${focusedCompany.name} · договоров: ${focusedContracts.length} · объектов: ${data.sites.filter((site) => site.company_id === focusedCompany.id).length}`
              : `Контекст ${focusedEntityType} ${focusedEntityId.slice(0, 8)} загружается...`}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {focusSummaryLink ? (
              <Button size="sm" variant={focusedView === "summary" ? "default" : "outline"} asChild>
                <Link to={focusSummaryLink}>Сводка</Link>
              </Button>
            ) : null}
            {focusTimelineLink ? (
              <Button size="sm" variant={focusedView === "timeline" ? "default" : "outline"} asChild>
                <Link to={focusTimelineLink}>Хронология</Link>
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" asChild>
              <Link to="/contractors">Сбросить фокус</Link>
            </Button>
          </div>
          {focusedView === "timeline" && focusedCompany ? (
            <div className="mt-3 space-y-2">
              {focusedContracts.length ? (
                focusedContracts.slice(0, 5).map((contract) => (
                  <div key={contract.id} className="rounded-md border p-2 text-xs">
                    <div className="font-medium">Договор {contract.number ?? contract.id.slice(0, 8)}</div>
                    <div className="text-muted-foreground">{contract.status} · истекает: {contract.expires_at ?? "не задано"}</div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground">Для выбранного контрагента договоры не найдены.</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
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
