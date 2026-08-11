import { useCallback, useEffect, useMemo, useState } from "react";

import { normalizeCompanyRead } from "@/api/companiesApi";
import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { BranchFormDialog } from "@/features/branches/BranchFormDialog";
import { BranchTable } from "@/features/branches/BranchTable";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useBranchesStore } from "@/stores/branches";
import type { CompanyDto } from "@/types/dto/companies";

const BranchesPage = () => {
  const { list, items, loading, error, setFilters, filters } = useBranchesStore();
  const { can } = useAbility();
  const canManage = can(PERMISSIONS.BRANCH_MANAGE);

  const [companies, setCompanies] = useState<CompanyDto[]>([]);

  useEffect(() => {
    let active = true;
    apiClient
      .get<{ items?: unknown[] }>("/companies", { params: { limit: 200, offset: 0 } })
      .then(({ data }) => {
        if (!active) return;
        const rows = Array.isArray(data?.items) ? data.items : [];
        setCompanies(rows.map((row) => normalizeCompanyRead(row)));
      })
      .catch(() => {
        if (active) setCompanies([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void list().catch(() => undefined);
  }, [list]);

  const handleCompanyFilter = useCallback(
    (companyId: string) => {
      setFilters({ company_id: companyId || undefined });
      void list({ company_id: companyId || undefined }).catch(() => undefined);
    },
    [setFilters, list]
  );

  const isEmpty = useMemo(() => !loading && !error && items.length === 0, [loading, error, items]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Филиалы" }]} />
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Филиалы</h1>
          <Can permission={PERMISSIONS.BRANCH_MANAGE}>
            {(allowed) => (
              <BranchFormDialog
                companies={companies}
                defaultCompanyId={filters.company_id}
                trigger={
                  <Button
                    disabled={!allowed || companies.length === 0}
                    title={
                      companies.length === 0
                        ? "Сначала создайте компанию"
                        : !allowed
                          ? "Недостаточно прав для создания филиала"
                          : undefined
                    }
                  >
                    Новый филиал
                  </Button>
                }
                onSubmitted={() => void list().catch(() => undefined)}
              />
            )}
          </Can>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-4 py-6">
          <div className="flex flex-col gap-2 sm:max-w-xs">
            <Label htmlFor="branch-company-filter">Компания</Label>
            <select
              id="branch-company-filter"
              className="h-10 rounded-md border px-3"
              value={filters.company_id ?? ""}
              onChange={(e) => handleCompanyFilter(e.target.value)}
            >
              <option value="">Все компании</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>

          <ErrorState error={error ?? undefined} onRetry={() => void list().catch(() => undefined)} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка филиалов" /> : null}
          {isEmpty ? (
            <EmptyState
              title="Филиалы не найдены"
              description="Создайте первый филиал или измените фильтр по компании."
            />
          ) : null}
          {!loading || items.length > 0 ? (
            <BranchTable companies={companies} canManage={canManage} />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default BranchesPage;
