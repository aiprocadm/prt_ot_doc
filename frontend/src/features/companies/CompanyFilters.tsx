import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyStatus } from "@/types/dto/companies";

const statuses: { label: string; value?: CompanyStatus }[] = [
  { label: "Все" },
  { label: "Активные", value: "active" },
  { label: "Черновики", value: "draft" },
  { label: "Архив", value: "archived" },
];

export const CompanyFilters = () => {
  const { filters, setFilters, list } = useCompaniesStore();
  const [localSearch, setLocalSearch] = useState(filters.search ?? "");
  const [localStatus, setLocalStatus] = useState<CompanyStatus | undefined>(
    filters.status,
  );

  useEffect(() => {
    setLocalSearch(filters.search ?? "");
    setLocalStatus(filters.status);
  }, [filters.search, filters.status]);

  const handleApply = () => {
    setFilters({ search: localSearch || undefined, status: localStatus });
    list();
  };

  const handleReset = () => {
    setLocalSearch("");
    setLocalStatus(undefined);
    setFilters({ search: undefined, status: undefined });
    list({ search: undefined, status: undefined });
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => event.preventDefault()}
      aria-label="Фильтры компаний"
    >
      <div className="space-y-2">
        <Label htmlFor="company-search">Поиск</Label>
        <Input
          id="company-search"
          value={localSearch}
          placeholder="Название, ИНН, тег"
          onChange={(event) => setLocalSearch(event.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label>Статус</Label>
        <div className="flex flex-col space-y-1">
          {statuses.map((status) => (
            <label
              key={status.label}
              className="inline-flex items-center gap-2 text-sm"
            >
              <input
                type="radio"
                name="company-status"
                value={status.value ?? ""}
                checked={
                  status.value === localStatus ||
                  (!status.value && !localStatus)
                }
                onChange={() => setLocalStatus(status.value)}
              />
              <span>{status.label}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" className="flex-1" onClick={handleApply}>
          Применить
        </Button>
        <Button type="button" variant="outline" onClick={handleReset}>
          Сбросить
        </Button>
      </div>
    </form>
  );
};
