import { useEffect, useMemo, useState } from "react";

import { warehouseApi, type StockBatchDto, type StockLevelDto } from "@/api/warehouse";
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
  const [levels, setLevels] = useState<StockLevelDto[]>([]);
  const [batches, setBatches] = useState<StockBatchDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [levelsData, batchesData] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches()
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить склад СИЗ" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const totalQuantity = useMemo(
    () => levels.reduce((sum, level) => sum + level.total_quantity, 0),
    [levels]
  );

  const rows = useMemo(() => {
    return levels.map((level) => {
      const status = level.total_quantity <= 0 ? "warning" : "ready";
      const searchBlob = [level.item_name, level.item_id].filter(Boolean).join(" ").toLowerCase();
      return {
        id: level.item_id,
        name: level.item_name,
        quantity: level.total_quantity,
        batchCount: level.batch_count,
        nearestExpiry: level.nearest_certificate_expiry ?? null,
        status,
        searchBlob
      };
    });
  }, [levels]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((item) => item.searchBlob.includes(normalized));
  }, [query, rows]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Склад СИЗ"
        description="Остатки и партии СИЗ по текущему тенанту (учёт партий, сроки сертификатов)."
        actions={<Badge variant="secondary">Партий: {batches.length}</Badge>}
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Позиции на складе</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : levels.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Суммарный остаток</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : totalQuantity}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Партий всего</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{loading ? "—" : batches.length}</CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Остатки по номенклатуре</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            placeholder="Поиск по номенклатуре"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка склада СИЗ" /> : null}
          {!loading && !error && filtered.length === 0 ? (
            <EmptyState
              title="Позиции не найдены"
              description={query ? "Измените запрос поиска." : "В tenant ещё нет партий СИЗ на складе."}
            />
          ) : null}
          {!loading && !error && filtered.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Номенклатура</TableHead>
                  <TableHead>Остаток</TableHead>
                  <TableHead>Партий</TableHead>
                  <TableHead>Ближайшее истечение</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.name}</TableCell>
                    <TableCell>{item.quantity}</TableCell>
                    <TableCell>{item.batchCount}</TableCell>
                    <TableCell>{formatDate(item.nearestExpiry) || "—"}</TableCell>
                    <TableCell>
                      <StatusBadge status={item.status} />
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
