import { useEffect, useMemo, useState } from "react";

import {
  warehouseApi,
  type InventoryCountDetailDto,
  type InventoryCountDto,
  type PPEStockShortageDto,
  type StockBatchDto,
  type StockLevelDto,
  type StockMovementDto
} from "@/api/warehouse";
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
  const [shortages, setShortages] = useState<PPEStockShortageDto[]>([]);
  const [form, setForm] = useState({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
  const [submitting, setSubmitting] = useState(false);
  const [counts, setCounts] = useState<InventoryCountDto[]>([]);
  const [activeCount, setActiveCount] = useState<InventoryCountDetailDto | null>(null);
  const [countForm, setCountForm] = useState({ scope_item_id: "", scope_location: "", note: "" });
  const [countedInputs, setCountedInputs] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [levelsData, batchesData, movementsData, shortagesData, countsData] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches(),
        warehouseApi.listMovements(),
        warehouseApi.listShortages(),
        warehouseApi.listCounts()
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
      setMovements(movementsData);
      setShortages(shortagesData);
      setCounts(countsData);
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

  const openCountDetail = (detail: InventoryCountDetailDto) => {
    setActiveCount(detail);
    const seeded: Record<string, string> = {};
    detail.lines.forEach((line) => {
      seeded[line.id] = line.counted_qty === null ? "" : String(line.counted_qty);
    });
    setCountedInputs(seeded);
  };

  const createCount = async () => {
    setSubmitting(true);
    try {
      const detail = await warehouseApi.createCount({
        scope_item_id: countForm.scope_item_id || null,
        scope_location: countForm.scope_location || null,
        note: countForm.note || null
      });
      setCountForm({ scope_item_id: "", scope_location: "", note: "" });
      openCountDetail(detail);
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось создать инвентаризацию" });
    } finally {
      setSubmitting(false);
    }
  };

  const openCount = async (id: string) => {
    try {
      openCountDetail(await warehouseApi.getCount(id));
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось открыть инвентаризацию" });
    }
  };

  const saveCounts = async () => {
    if (!activeCount) return;
    setSubmitting(true);
    try {
      const entries = activeCount.lines.map((line) => ({
        line_id: line.id,
        counted_qty:
          countedInputs[line.id] === "" || countedInputs[line.id] === undefined
            ? null
            : Number(countedInputs[line.id])
      }));
      openCountDetail(await warehouseApi.patchCountLines(activeCount.id, entries));
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось сохранить факт" });
    } finally {
      setSubmitting(false);
    }
  };

  const applyActiveCount = async () => {
    if (!activeCount) return;
    setSubmitting(true);
    try {
      openCountDetail(await warehouseApi.applyCount(activeCount.id));
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось применить инвентаризацию" });
    } finally {
      setSubmitting(false);
    }
  };

  const cancelActiveCount = async () => {
    if (!activeCount) return;
    setSubmitting(true);
    try {
      openCountDetail(await warehouseApi.cancelCount(activeCount.id));
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось отменить инвентаризацию" });
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
          <p className="text-xs text-muted-foreground">
            Для «Корректировки» количество — это фактический остаток партии (не дельта).
          </p>
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
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Дефицит / мин-остаток
            <Badge variant="secondary">{shortages.filter((s) => s.below_threshold).length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {shortages.length === 0 ? (
            <EmptyState
              title="Дефицита нет"
              description="Все позиции выше минимального остатка."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Позиция</TableHead>
                  <TableHead>Остаток</TableHead>
                  <TableHead>Порог</TableHead>
                  <TableHead>Дефицит</TableHead>
                  <TableHead>Дней до исчерпания</TableHead>
                  <TableHead>Дата пробоя</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shortages.map((s) => (
                  <TableRow key={s.item_id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {s.item_name}
                        <Badge variant={s.below_threshold ? "destructive" : "secondary"}>
                          {s.below_threshold ? "Дефицит" : "Норма"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>{s.on_hand}</TableCell>
                    <TableCell>{s.min_stock}</TableCell>
                    <TableCell>{s.deficit}</TableCell>
                    <TableCell>
                      {s.days_to_depletion !== null ? Math.round(s.days_to_depletion) : "—"}
                    </TableCell>
                    <TableCell>
                      {s.projected_breach_date !== null ? formatDate(s.projected_breach_date) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Инвентаризация
            <Badge variant="secondary">{counts.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 items-end">
            <Input
              placeholder="ID позиции (опц.)"
              value={countForm.scope_item_id}
              onChange={(e) => setCountForm({ ...countForm, scope_item_id: e.target.value })}
            />
            <Input
              placeholder="Локация (опц.)"
              value={countForm.scope_location}
              onChange={(e) => setCountForm({ ...countForm, scope_location: e.target.value })}
            />
            <Input
              placeholder="Заметка (опц.)"
              value={countForm.note}
              onChange={(e) => setCountForm({ ...countForm, note: e.target.value })}
            />
            <Button onClick={createCount} disabled={submitting}>
              Создать
            </Button>
          </div>

          {counts.length === 0 ? (
            <EmptyState title="Нет инвентаризаций" description="Создайте срез для сверки факта." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Статус</TableHead>
                  <TableHead>Заметка</TableHead>
                  <TableHead>Строк</TableHead>
                  <TableHead>Сосчитано</TableHead>
                  <TableHead>Создан</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {counts.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Badge variant={c.status === "applied" ? "secondary" : "outline"}>
                        {c.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{c.note || "—"}</TableCell>
                    <TableCell>{c.line_count}</TableCell>
                    <TableCell>{c.counted_count}</TableCell>
                    <TableCell>{formatDate(c.created_at) || "—"}</TableCell>
                    <TableCell>
                      <Button variant="outline" onClick={() => openCount(c.id)}>
                        Открыть
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {activeCount ? (
            <div className="space-y-3 border-t pt-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">Строки инвентаризации</span>
                <Badge variant="outline">{activeCount.status}</Badge>
                <Badge variant="secondary">расхождений: {activeCount.diff_count}</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Партия</TableHead>
                    <TableHead>Локация</TableHead>
                    <TableHead>Система</TableHead>
                    <TableHead>Остаток</TableHead>
                    <TableHead>Факт</TableHead>
                    <TableHead>Δ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeCount.lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell className="font-medium">{line.batch_no}</TableCell>
                      <TableCell>{line.location || "—"}</TableCell>
                      <TableCell>{line.system_qty}</TableCell>
                      <TableCell>{line.on_hand}</TableCell>
                      <TableCell>
                        <Input
                          aria-label={`Факт ${line.batch_no}`}
                          value={countedInputs[line.id] ?? ""}
                          disabled={activeCount.status !== "draft"}
                          onChange={(e) =>
                            setCountedInputs({ ...countedInputs, [line.id]: e.target.value })
                          }
                        />
                      </TableCell>
                      <TableCell>{line.delta === null ? "—" : line.delta}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {activeCount.status === "draft" ? (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={saveCounts} disabled={submitting}>
                    Сохранить факт
                  </Button>
                  <Button onClick={applyActiveCount} disabled={submitting}>
                    Применить
                  </Button>
                  <Button variant="ghost" onClick={cancelActiveCount} disabled={submitting}>
                    Отменить
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default WarehousePage;
