import { useEffect, useMemo, useState } from "react";

import { opsApi, type PpeIssueDto, type PpeItemDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const WarehousePage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PpeItemDto[]>([]);
  const [expiring, setExpiring] = useState<PpeIssueDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await opsApi.getPpeOverview();
      setItems(snapshot.items);
      setExpiring(snapshot.expiring);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить складские остатки" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const expiringByItemId = useMemo(() => {
    const map = new Map<string, PpeIssueDto[]>();
    expiring.forEach((issue) => {
      map.set(issue.item_id, [...(map.get(issue.item_id) ?? []), issue]);
    });
    return map;
  }, [expiring]);

  const rows = useMemo(() => {
    return items.map((item) => {
      const relatedExpiring = expiringByItemId.get(item.id) ?? [];
      const defaultWearDays = item.default_wear_days ?? 0;
      const nearestExpiry = relatedExpiring
        .map((issue) => issue.expires_at)
        .filter(Boolean)
        .sort()[0] ?? null;
      const status = relatedExpiring.length > 0 ? "warning" : defaultWearDays <= 0 ? "draft" : "ready";
      const searchBlob = [item.code, item.name, item.category, item.description].filter(Boolean).join(" ").toLowerCase();
      return {
        id: item.id,
        sku: item.code,
        name: item.name,
        category: item.category,
        wearDays: defaultWearDays,
        certificate: nearestExpiry,
        expiringCount: relatedExpiring.length,
        status,
        searchBlob
      };
    });
  }, [expiringByItemId, items]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((item) => item.searchBlob.includes(normalized));
  }, [query, rows]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Склад СИЗ"
        description="Остатки каталога СИЗ и истекающие выдачи по текущему тенанту на основе реальных PPE API."
        actions={<Badge variant="secondary">Истекающих выдач: {expiring.length}</Badge>}
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Позиции каталога</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : items.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Истекают в 30 дней</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : expiring.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Без срока носки</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : items.filter((item) => !item.default_wear_days).length}</CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Номенклатура и риск истечения</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Поиск по SKU, названию, категории" value={query} onChange={(event) => setQuery(event.target.value)} />
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка склада СИЗ" /> : null}
          {!loading && !error && filtered.length === 0 ? (
            <EmptyState
              title="Позиции не найдены"
              description={query ? "Измените запрос поиска." : "В tenant ещё нет позиций СИЗ."}
            />
          ) : null}
          {!loading && !error && filtered.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Номенклатура</TableHead>
                  <TableHead>Категория</TableHead>
                  <TableHead>Срок носки</TableHead>
                  <TableHead>Ближайшее истечение</TableHead>
                  <TableHead>Риск</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.sku}</TableCell>
                    <TableCell>{item.name}</TableCell>
                    <TableCell>{item.category}</TableCell>
                    <TableCell>{item.wearDays > 0 ? `${item.wearDays} дн.` : "Не задан"}</TableCell>
                    <TableCell>{formatDate(item.certificate) || "—"}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={item.status} />
                        {item.expiringCount > 0 ? <span className="text-xs text-muted-foreground">{item.expiringCount} выдач</span> : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default WarehousePage;
