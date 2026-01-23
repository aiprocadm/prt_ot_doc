import { useCallback, useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CompanyDetails } from "@/features/companies/CompanyDetails";
import { CompanyFilters } from "@/features/companies/CompanyFilters";
import { CompanyFormDialog } from "@/features/companies/CompanyFormDialog";
import { CompanyTable } from "@/features/companies/CompanyTable";
import { useSidebar } from "@/layouts/MainLayout";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyDto } from "@/types/dto/companies";

const CompaniesPage = () => {
  const { list, getById } = useCompaniesStore();
  const { setSidebar } = useSidebar();
  const [selectedCompany, setSelectedCompany] = useState<CompanyDto | null>(null);

  useEffect(() => {
    setSidebar(<CompanyFilters />);
    return () => setSidebar(null);
  }, [setSidebar]);

  useEffect(() => {
    list();
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
          <CompanyFormDialog
            trigger={<Button>Новая компания</Button>}
            onSubmitted={(company) => {
              setSelectedCompany(company);
              list();
            }}
          />
        </div>
      </div>
      <Card>
        <CardContent className="py-6">
          <CompanyTable onSelect={handleSelect} />
        </CardContent>
      </Card>
      {selectedCompany && <CompanyDetails company={selectedCompany} />}
    </div>
  );
};

export default CompaniesPage;
