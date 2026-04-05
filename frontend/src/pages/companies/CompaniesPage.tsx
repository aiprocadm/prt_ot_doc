import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CompanyDetails } from "@/features/companies/CompanyDetails";
import { CompanyFilters } from "@/features/companies/CompanyFilters";
import { CompanyFormDialog } from "@/features/companies/CompanyFormDialog";
import { CompanyTable } from "@/features/companies/CompanyTable";
import { useSidebar } from "@/layouts/MainLayout";
import { PERMISSIONS } from "@/permissions/permissions";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyDto } from "@/types/dto/companies";

const CompaniesPage = () => {
  const { list, getById, items, loading, error } = useCompaniesStore();
  const { setSidebar } = useSidebar();
  const [selectedCompany, setSelectedCompany] = useState<CompanyDto | null>(null);

  useEffect(() => {
    setSidebar(<CompanyFilters />);
    return () => setSidebar(null);
  }, [setSidebar]);

  useEffect(() => {
    void list().catch(() => undefined);
  }, [list]);

  const handleSelect = useCallback(
    async (company: CompanyDto) => {
      const full = await getById(company.id);
      setSelectedCompany(full ?? company);
    },
    [getById]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Компании" }]} />
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Компании</h1>
          <Can permission={PERMISSIONS.COMPANY_CREATE}>
            {(allowed) => (
              <CompanyFormDialog
                trigger={
                  <Button
                    disabled={!allowed}
                    title={!allowed ? "Недостаточно прав для создания компании" : undefined}
                  >
                    Новая компания
                  </Button>
                }
                onSubmitted={(company) => {
                  setSelectedCompany(company);
                  list();
                }}
              />
            )}
          </Can>
        </div>
      </div>
      <Card>
        <CardContent className="py-6">
          <ErrorState error={error ?? undefined} onRetry={() => void list().catch(() => undefined)} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка компаний" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Компании не найдены" description="Создайте первую компанию или измените фильтры в боковой панели." />
          ) : null}
          {!loading || items.length > 0 ? <CompanyTable onSelect={handleSelect} /> : null}
        </CardContent>
      </Card>
      {selectedCompany && <CompanyDetails company={selectedCompany} />}
    </div>
  );
};

export default CompaniesPage;
