import { useMemo, useState } from "react";

import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const stockRows = [
  { sku: "PPE-001", name: "Каска защитная", batch: "B-2304", qty: 142, status: "ready", certificate: "до 12.2027" },
  { sku: "PPE-014", name: "Перчатки термостойкие", batch: "B-2309", qty: 23, status: "warning", certificate: "до 02.2026" },
  { sku: "PPE-031", name: "Респиратор FFP3", batch: "B-2401", qty: 0, status: "overdue", certificate: "до 11.2025" }
] as const;

const WarehousePage = () => {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return stockRows;
    return stockRows.filter((item) => `${item.sku} ${item.name} ${item.batch}`.toLowerCase().includes(normalized));
  }, [query]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Склад СИЗ"
        description="Остатки, партии и контроль сертификатов по текущему тенанту."
        actions={<Badge variant="secondary">X-Tenant scope enabled</Badge>}
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Остатки и партии</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Поиск по SKU, названию, партии" value={query} onChange={(event) => setQuery(event.target.value)} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>SKU</TableHead>
                <TableHead>Номенклатура</TableHead>
                <TableHead>Партия</TableHead>
                <TableHead>Остаток</TableHead>
                <TableHead>Сертификат</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((item) => (
                <TableRow key={`${item.sku}-${item.batch}`}>
                  <TableCell className="font-medium">{item.sku}</TableCell>
                  <TableCell>{item.name}</TableCell>
                  <TableCell>{item.batch}</TableCell>
                  <TableCell>{item.qty}</TableCell>
                  <TableCell>{item.certificate}</TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default WarehousePage;
