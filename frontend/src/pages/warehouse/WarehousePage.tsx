import { useEffect, useMemo, useState } from "react";

import { warehouseApi, type StockBatchDto, type StockLevelDto, type StockMovementDto } from "@/api/warehouse";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [form, setForm] = useState({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [levelsData, batchesData, movementsData] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches(),
        warehouseApi.listMovements()
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
      setMovements(movementsData);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить склад СИЗ" });
    } finally {
      setLoading(false);
    }
  };

  const submitMovement = async () => {
    if (!form.batch_id) return;
    setSubmitting(true);
    try {
      await warehouseApi.createMovement({
        batch_id: form.batch_id,
        kind: form.kind as "receipt" | "writeoff" | "adjustment",
        quantity: Number(form.quantity) || 0,
        reason: form.reason || null
      });
      setForm({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось провести движение" });
    } finally {
      setSubmitting(false);
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
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Движения</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-5">
            <Input
              placeholder="ID партии"
              value={form.batch_id}
              onChange={(e) => setForm({ ...form, batch_id: e.target.value })}
            />
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              <option value="receipt">Приход</option>
              <option value="writeoff">Списание</option>
              <option value="adjustment">Корректировка (до факт.)</option>
            </select>
            <Input
              type="number"
              min={0}
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
            <Input
              placeholder="Причина"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <Button onClick={submitMovement} disabled={submitting || !form.batch_id}>
              Провести
            </Button>
          </div>
          {movements.length === 0 ? (
            <EmptyState title="Движений нет" description="Проведите приход или корректировку по партии." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Δ Кол-во</TableHead>
                  <TableHead>Причина</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {movements.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{formatDate(m.occurred_at) || "—"}</TableCell>
                    <TableCell>{m.kind}</TableCell>
                    <TableCell>{m.quantity_delta}</TableCell>
                    <TableCell>{m.reason || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default WarehousePage;
