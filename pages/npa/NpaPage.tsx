import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useNpaStore } from "@/stores/npa";
import type { NpaStatus } from "@/types/dto/npa";
import { NpaTable } from "@/features/npa/NpaTable";

const NpaPage = () => {
  const { list, setFilters, filters } = useNpaStore();
  const [search, setSearch] = useState(filters.search ?? "");
  const [status, setStatus] = useState<NpaStatus | "">(filters.status ?? "");

  useEffect(() => {
    list();
  }, [list]);

  const applyFilters = () => {
    setFilters({ search: search || undefined, status: status || undefined });
    list();
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "НПА" }]} />
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-6">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="npa-search">
              Поиск
            </label>
            <Input id="npa-search" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="npa-status">
              Статус
            </label>
            <select id="npa-status" className="h-10 rounded-md border px-3" value={status} onChange={(event) => setStatus(event.target.value as NpaStatus | "")}
            >
              <option value="">Все</option>
              <option value="active">Действует</option>
              <option value="obsolete">Недействует</option>
              <option value="draft">Проект</option>
            </select>
          </div>
          <Button onClick={applyFilters}>Применить</Button>
        </CardContent>
      </Card>
      <NpaTable />
    </div>
  );
};

export default NpaPage;
