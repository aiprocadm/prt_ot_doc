import { useEffect, useMemo, useState } from "react";

import {
  warehouseApi,
  type BudgetDetailDto,
  type BudgetDto,
  type CreateTransferInput,
  type InventoryCountDetailDto,
  type InventoryCountDto,
  type PPEStockShortageDto,
  type ReorderDraftDto,
  type StockBatchDto,
  type StockLevelByLocationDto,
  type StockLevelDto,
  type StockMovementDto,
  type StockTransferDto,
  type SupplierDto,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const csvCell = (v: string | number | null | undefined): string => {
  const s = String(v ?? "");
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const WarehousePage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [levels, setLevels] = useState<StockLevelDto[]>([]);
  const [batches, setBatches] = useState<StockBatchDto[]>([]);
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [shortages, setShortages] = useState<PPEStockShortageDto[]>([]);
  const [form, setForm] = useState({
    batch_id: "",
    kind: "receipt",
    quantity: "1",
    reason: "",
  });
  const [submitting, setSubmitting] = useState(false);
  // BIZ-59 (разд. 59.1 «одна задача — один экран»): шесть рабочих форм
  // висели на экране одновременно — 27 полей и шесть главных действий.
  // Открыт всегда ОДИН раздел: кладовщик приходит с одной задачей.
  // Обзор (остатки, дефицит, дозаказ) — чтение, он виден всегда.
  const [openSection, setOpenSection] = useState<
    | "movement"
    | "transfer"
    | "supplier"
    | "batch"
    | "inventory"
    | "budget"
    | null
  >(null);
  const [counts, setCounts] = useState<InventoryCountDto[]>([]);
  const [transfers, setTransfers] = useState<StockTransferDto[]>([]);
  const [levelsByLoc, setLevelsByLoc] = useState<StockLevelByLocationDto[]>([]);
  const [transferForm, setTransferForm] = useState({
    source_batch_id: "",
    to_location: "",
    quantity: "1",
    reason: "",
  });
  const [transferSubmitting, setTransferSubmitting] = useState(false);
  const [activeCount, setActiveCount] =
    useState<InventoryCountDetailDto | null>(null);
  const [countForm, setCountForm] = useState({
    scope_item_id: "",
    scope_location: "",
    note: "",
  });
  const [countedInputs, setCountedInputs] = useState<Record<string, string>>(
    {},
  );
  const [suppliers, setSuppliers] = useState<SupplierDto[]>([]);
  const [supplierForm, setSupplierForm] = useState({
    id: "",
    name: "",
    inn: "",
    contact_email: "",
    contact_phone: "",
  });
  const [reorderDraft, setReorderDraft] = useState<ReorderDraftDto | null>(
    null,
  );
  const [batchForm, setBatchForm] = useState({
    item_id: "",
    batch_no: "",
    quantity: "1",
    location: "",
    supplier_id: "",
    unit_cost: "",
  });
  const [budgets, setBudgets] = useState<BudgetDto[]>([]);
  const [budgetForm, setBudgetForm] = useState({
    name: "",
    period_start: "",
    period_end: "",
    planned_amount: "",
    notes: "",
  });
  const [activeBudget, setActiveBudget] = useState<BudgetDetailDto | null>(
    null,
  );

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        levelsData,
        batchesData,
        movementsData,
        shortagesData,
        countsData,
        transfersData,
        levelsByLocData,
        suppliersData,
        reorderData,
        budgetsData,
      ] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches(),
        warehouseApi.listMovements(),
        warehouseApi.listShortages(),
        warehouseApi.listCounts(),
        warehouseApi.listTransfers(),
        warehouseApi.listLevelsByLocation(),
        warehouseApi.listSuppliers(),
        warehouseApi.getReorderDraft(),
        warehouseApi.listBudgets(),
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
      setMovements(movementsData);
      setShortages(shortagesData);
      setCounts(countsData);
      setTransfers(transfersData);
      setLevelsByLoc(levelsByLocData);
      setSuppliers(suppliersData);
      setReorderDraft(reorderData);
      setBudgets(budgetsData);
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось загрузить склад СИЗ" },
      );
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
        reason: form.reason || null,
      });
      setForm({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
      await load();
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось провести движение" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submitTransfer = async () => {
    if (!transferForm.source_batch_id || !transferForm.to_location) return;
    setTransferSubmitting(true);
    setError(null);
    try {
      const body: CreateTransferInput = {
        source_batch_id: transferForm.source_batch_id.trim(),
        to_location: transferForm.to_location.trim(),
        quantity: Number(transferForm.quantity) || 0,
        reason: transferForm.reason || null,
      };
      await warehouseApi.createTransfer(body);
      setTransferForm({
        source_batch_id: "",
        to_location: "",
        quantity: "1",
        reason: "",
      });
      await load();
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось выполнить перемещение" },
      );
    } finally {
      setTransferSubmitting(false);
    }
  };

  const knownLocations = useMemo(
    () =>
      Array.from(
        new Set(levelsByLoc.map((l) => l.location).filter(Boolean)),
      ) as string[],
    [levelsByLoc],
  );

  const openCountDetail = (detail: InventoryCountDetailDto) => {
    setActiveCount(detail);
    const seeded: Record<string, string> = {};
    detail.lines.forEach((line) => {
      seeded[line.id] =
        line.counted_qty === null ? "" : String(line.counted_qty);
    });
    setCountedInputs(seeded);
  };

  const createCount = async () => {
    setSubmitting(true);
    try {
      const detail = await warehouseApi.createCount({
        scope_item_id: countForm.scope_item_id || null,
        scope_location: countForm.scope_location || null,
        note: countForm.note || null,
      });
      setCountForm({ scope_item_id: "", scope_location: "", note: "" });
      openCountDetail(detail);
      await load();
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось создать инвентаризацию" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const openCount = async (id: string) => {
    try {
      openCountDetail(await warehouseApi.getCount(id));
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось открыть инвентаризацию" },
      );
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
            : Number(countedInputs[line.id]),
      }));
      openCountDetail(
        await warehouseApi.patchCountLines(activeCount.id, entries),
      );
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
      setError(
        (err as ApiError) ?? { message: "Не удалось применить инвентаризацию" },
      );
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
      setError(
        (err as ApiError) ?? { message: "Не удалось отменить инвентаризацию" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submitSupplier = async () => {
    if (!supplierForm.name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        name: supplierForm.name.trim(),
        inn: supplierForm.inn.trim() || null,
        contact_email: supplierForm.contact_email.trim() || null,
        contact_phone: supplierForm.contact_phone.trim() || null,
      };
      if (supplierForm.id) {
        await warehouseApi.updateSupplier(supplierForm.id, payload);
      } else {
        await warehouseApi.createSupplier(payload);
      }
      setSupplierForm({
        id: "",
        name: "",
        inn: "",
        contact_email: "",
        contact_phone: "",
      });
      await load();
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось сохранить поставщика" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const editSupplier = (supplier: SupplierDto) => {
    setSupplierForm({
      id: supplier.id,
      name: supplier.name,
      inn: supplier.inn ?? "",
      contact_email: supplier.contact_email ?? "",
      contact_phone: supplier.contact_phone ?? "",
    });
  };

  const removeSupplier = async (id: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await warehouseApi.deleteSupplier(id);
      await load();
    } catch (err) {
      setError(
        (err as ApiError) ?? { message: "Не удалось удалить поставщика" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submitBatch = async () => {
    if (!batchForm.item_id.trim() || !batchForm.batch_no.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await warehouseApi.createBatch({
        item_id: batchForm.item_id.trim(),
        batch_no: batchForm.batch_no.trim(),
        quantity: Number(batchForm.quantity) || 0,
        location: batchForm.location.trim() || null,
        supplier_id: batchForm.supplier_id || null,
        unit_cost:
          batchForm.unit_cost.trim() === ""
            ? null
            : Number(batchForm.unit_cost),
      });
      setBatchForm({
        item_id: "",
        batch_no: "",
        quantity: "1",
        location: "",
        supplier_id: "",
        unit_cost: "",
      });
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось создать партию" });
    } finally {
      setSubmitting(false);
    }
  };

  const changePreferredSupplier = async (
    itemId: string,
    supplierId: string | null,
  ) => {
    setError(null);
    try {
      await warehouseApi.patchItemPreferredSupplier(itemId, supplierId);
      // Both the shortages and reorder-draft views derive from the same supplier
      // resolution, so refresh both to keep them consistent after the change.
      const [freshShortages, freshReorder] = await Promise.all([
        warehouseApi.listShortages(),
        warehouseApi.getReorderDraft(),
      ]);
      setShortages(freshShortages);
      setReorderDraft(freshReorder);
    } catch (err) {
      setError(
        (err as ApiError) ?? {
          message: "Не удалось задать поставщика позиции",
        },
      );
    }
  };

  const submitBudget = async () => {
    if (
      !budgetForm.name.trim() ||
      !budgetForm.period_start ||
      !budgetForm.period_end
    )
      return;
    setSubmitting(true);
    setError(null);
    try {
      await warehouseApi.createBudget({
        name: budgetForm.name.trim(),
        period_start: budgetForm.period_start,
        period_end: budgetForm.period_end,
        planned_amount: Number(budgetForm.planned_amount) || 0,
        notes: budgetForm.notes.trim() || null,
      });
      setBudgetForm({
        name: "",
        period_start: "",
        period_end: "",
        planned_amount: "",
        notes: "",
      });
      const fresh = await warehouseApi.listBudgets();
      setBudgets(fresh);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось создать бюджет" });
    } finally {
      setSubmitting(false);
    }
  };

  const openBudget = async (id: string) => {
    setError(null);
    try {
      setActiveBudget(await warehouseApi.getBudget(id));
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось открыть бюджет" });
    }
  };

  const copyReorderDraft = async () => {
    if (!reorderDraft) return;
    const lines: string[] = ["Поставщик;ИНН;Контакт;Позиция;Дефицит"];
    reorderDraft.groups.forEach((group) => {
      const supplierName = group.supplier_name ?? "Без поставщика";
      group.lines.forEach((line) => {
        lines.push(
          [
            csvCell(supplierName),
            csvCell(group.supplier_inn),
            csvCell(group.supplier_contact),
            csvCell(line.item_name),
            csvCell(line.deficit),
          ].join(";"),
        );
      });
    });
    const csv = lines.join("\n");
    try {
      await navigator.clipboard?.writeText(csv);
    } catch {
      // clipboard may be unavailable (e.g. insecure context) — ignore silently
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const totalQuantity = useMemo(
    () => levels.reduce((sum, level) => sum + level.total_quantity, 0),
    [levels],
  );

  const rows = useMemo(() => {
    return levels.map((level) => {
      const status = level.total_quantity <= 0 ? "warning" : "ready";
      const searchBlob = [level.item_name, level.item_id]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return {
        id: level.item_id,
        name: level.item_name,
        quantity: level.total_quantity,
        batchCount: level.batch_count,
        nearestExpiry: level.nearest_certificate_expiry ?? null,
        status,
        searchBlob,
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
            <CardTitle className="text-sm text-muted-foreground">
              Позиции на складе
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : levels.length}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Суммарный остаток
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : totalQuantity}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Партий всего
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : batches.length}
          </CardContent>
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
              description={
                query
                  ? "Измените запрос поиска."
                  : "В tenant ещё нет партий СИЗ на складе."
              }
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
                    <TableCell>
                      {formatDate(item.nearestExpiry) || "—"}
                    </TableCell>
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
      <div
        className="flex flex-wrap gap-2"
        data-testid="warehouse-section-switch"
      >
        {(
          [
            ["movement", "Движения"],
            ["transfer", "Перемещение"],
            ["batch", "Приёмка партии"],
            ["inventory", "Инвентаризация"],
            ["supplier", "Поставщики"],
            ["budget", "Бюджет"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            size="sm"
            variant={openSection === key ? "secondary" : "outline"}
            onClick={() => setOpenSection(openSection === key ? null : key)}
          >
            {label}
          </Button>
        ))}
      </div>
      {openSection === "movement" ? (
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
              <Button
                onClick={submitMovement}
                disabled={submitting || !form.batch_id}
              >
                Провести
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Для «Корректировки» количество — это фактический остаток партии
              (не дельта).
            </p>
            {movements.length === 0 ? (
              <EmptyState
                title="Движений нет"
                description="Проведите приход или корректировку по партии."
              />
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
      ) : null}
      {openSection === "transfer" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Перемещения между локациями
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                aria-label="Партия-источник"
                placeholder="ID партии-источника"
                value={transferForm.source_batch_id}
                onChange={(e) =>
                  setTransferForm((f) => ({
                    ...f,
                    source_batch_id: e.target.value,
                  }))
                }
              />
              <Input
                aria-label="Куда (локация)"
                list="transfer-locations"
                placeholder="Локация назначения"
                value={transferForm.to_location}
                onChange={(e) =>
                  setTransferForm((f) => ({
                    ...f,
                    to_location: e.target.value,
                  }))
                }
              />
              <datalist id="transfer-locations">
                {knownLocations.map((loc) => (
                  <option key={loc} value={loc} />
                ))}
              </datalist>
              <Input
                aria-label="Количество для переноса"
                type="number"
                min={1}
                value={transferForm.quantity}
                onChange={(e) =>
                  setTransferForm((f) => ({ ...f, quantity: e.target.value }))
                }
              />
              <Input
                aria-label="Причина перемещения"
                placeholder="Причина (опционально)"
                value={transferForm.reason}
                onChange={(e) =>
                  setTransferForm((f) => ({ ...f, reason: e.target.value }))
                }
              />
            </div>
            <Button onClick={submitTransfer} disabled={transferSubmitting}>
              Перенести
            </Button>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Позиция</TableHead>
                  <TableHead>Партия</TableHead>
                  <TableHead>Маршрут</TableHead>
                  <TableHead>Кол-во</TableHead>
                  <TableHead>Когда</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transfers.map((t) => (
                  <TableRow key={t.ref_id}>
                    <TableCell>{t.item_name}</TableCell>
                    <TableCell>{t.batch_no}</TableCell>
                    <TableCell>
                      {t.from_location ?? "—"} → {t.to_location}
                    </TableCell>
                    <TableCell>{t.quantity}</TableCell>
                    <TableCell>{formatDate(t.occurred_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      {openSection === "supplier" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              Поставщики
              <Badge variant="secondary">{suppliers.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 md:grid-cols-5">
              <Input
                aria-label="Название поставщика"
                placeholder="Название"
                value={supplierForm.name}
                onChange={(e) =>
                  setSupplierForm((f) => ({ ...f, name: e.target.value }))
                }
              />
              <Input
                aria-label="ИНН поставщика"
                placeholder="ИНН"
                value={supplierForm.inn}
                onChange={(e) =>
                  setSupplierForm((f) => ({ ...f, inn: e.target.value }))
                }
              />
              <Input
                aria-label="Email поставщика"
                placeholder="Email"
                value={supplierForm.contact_email}
                onChange={(e) =>
                  setSupplierForm((f) => ({
                    ...f,
                    contact_email: e.target.value,
                  }))
                }
              />
              <Input
                aria-label="Телефон поставщика"
                placeholder="Телефон"
                value={supplierForm.contact_phone}
                onChange={(e) =>
                  setSupplierForm((f) => ({
                    ...f,
                    contact_phone: e.target.value,
                  }))
                }
              />
              <div className="flex gap-2">
                <Button
                  onClick={submitSupplier}
                  disabled={submitting || !supplierForm.name.trim()}
                >
                  Сохранить поставщика
                </Button>
                {supplierForm.id ? (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setSupplierForm({
                        id: "",
                        name: "",
                        inn: "",
                        contact_email: "",
                        contact_phone: "",
                      })
                    }
                  >
                    Отмена
                  </Button>
                ) : null}
              </div>
            </div>
            {suppliers.length === 0 ? (
              <EmptyState
                title="Поставщиков нет"
                description="Добавьте поставщика для дозаказа СИЗ."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Название</TableHead>
                    <TableHead>ИНН</TableHead>
                    <TableHead>Контакт</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {suppliers.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell>{s.inn || "—"}</TableCell>
                      <TableCell>
                        {s.contact_email || s.contact_phone || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            onClick={() => editSupplier(s)}
                          >
                            Изменить
                          </Button>
                          <Button
                            variant="ghost"
                            aria-label={`Удалить поставщика ${s.name}`}
                            onClick={() => removeSupplier(s.id)}
                            disabled={submitting}
                          >
                            Удалить
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      ) : null}
      {openSection === "batch" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Новая партия (приёмка)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 md:grid-cols-3">
              <Input
                aria-label="ID позиции партии"
                placeholder="ID позиции"
                value={batchForm.item_id}
                onChange={(e) =>
                  setBatchForm((f) => ({ ...f, item_id: e.target.value }))
                }
              />
              <Input
                aria-label="Номер партии"
                placeholder="Номер партии"
                value={batchForm.batch_no}
                onChange={(e) =>
                  setBatchForm((f) => ({ ...f, batch_no: e.target.value }))
                }
              />
              <Input
                aria-label="Количество партии"
                type="number"
                min={0}
                value={batchForm.quantity}
                onChange={(e) =>
                  setBatchForm((f) => ({ ...f, quantity: e.target.value }))
                }
              />
            </div>
            {/* BIZ-59 (разд. 59.3): необязательные реквизиты приёмки — на втором
              уровне. Партию принимают по позиции, номеру и количеству; локация,
              поставщик и цена дописываются, когда они вообще известны. */}
            <details className="space-y-2">
              <summary className="cursor-pointer text-sm text-muted-foreground">
                Дополнительно (локация, поставщик, цена)
              </summary>
              <div className="grid gap-2 pt-2 md:grid-cols-3">
                <Input
                  aria-label="Локация партии"
                  placeholder="Локация (опц.)"
                  value={batchForm.location}
                  onChange={(e) =>
                    setBatchForm((f) => ({ ...f, location: e.target.value }))
                  }
                />
                <select
                  aria-label="Поставщик партии"
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={batchForm.supplier_id}
                  onChange={(e) =>
                    setBatchForm((f) => ({ ...f, supplier_id: e.target.value }))
                  }
                >
                  <option value="">— без поставщика —</option>
                  {suppliers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <Input
                  aria-label="Цена за единицу"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="Цена за единицу"
                  value={batchForm.unit_cost}
                  onChange={(e) =>
                    setBatchForm((f) => ({ ...f, unit_cost: e.target.value }))
                  }
                />
              </div>
            </details>
            <Button
              onClick={submitBatch}
              disabled={
                submitting ||
                !batchForm.item_id.trim() ||
                !batchForm.batch_no.trim()
              }
            >
              Создать партию
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Дефицит / мин-остаток
            <Badge variant="secondary">
              {shortages.filter((s) => s.below_threshold).length}
            </Badge>
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
                  <TableHead>Поставщик</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shortages.map((s) => (
                  <TableRow key={s.item_id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {s.item_name}
                        <Badge
                          variant={
                            s.below_threshold ? "destructive" : "secondary"
                          }
                        >
                          {s.below_threshold ? "Дефицит" : "Норма"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>{s.on_hand}</TableCell>
                    <TableCell>{s.min_stock}</TableCell>
                    <TableCell>{s.deficit}</TableCell>
                    <TableCell>
                      {s.days_to_depletion !== null
                        ? Math.round(s.days_to_depletion)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {s.projected_breach_date !== null
                        ? formatDate(s.projected_breach_date)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        {s.supplier_name ? (
                          <div className="flex items-center gap-2">
                            <span>{s.supplier_name}</span>
                            {s.supplier_source === "explicit" ? (
                              <Badge variant="secondary">явный</Badge>
                            ) : s.supplier_source === "history" ? (
                              <Badge variant="outline">история</Badge>
                            ) : null}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                        <select
                          aria-label={`Предпочтительный поставщик ${s.item_name}`}
                          className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
                          value={
                            s.supplier_source === "explicit"
                              ? (s.supplier_id ?? "")
                              : ""
                          }
                          onChange={(e) =>
                            void changePreferredSupplier(
                              s.item_id,
                              e.target.value || null,
                            )
                          }
                        >
                          <option value="">— без явного —</option>
                          {suppliers.map((sup) => (
                            <option key={sup.id} value={sup.id}>
                              {sup.name}
                            </option>
                          ))}
                        </select>
                      </div>
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
          <CardTitle className="text-base flex items-center justify-between gap-2">
            <span className="flex items-center gap-2">
              Дозаказ
              <Badge variant="secondary">
                {reorderDraft?.total_lines ?? 0}
              </Badge>
            </span>
            <Button
              variant="outline"
              onClick={copyReorderDraft}
              disabled={!reorderDraft || reorderDraft.total_lines === 0}
            >
              Копировать CSV
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!reorderDraft || reorderDraft.groups.length === 0 ? (
            <EmptyState
              title="Дозаказ не требуется"
              description="Нет позиций с дефицитом ниже минимального остатка."
            />
          ) : (
            reorderDraft.groups.map((group) => (
              <div
                key={group.supplier_id ?? "no-supplier"}
                className="space-y-2 rounded-md border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {group.supplier_name ?? "Без поставщика"}
                  </span>
                  {group.supplier_contact ? (
                    <span className="text-sm text-muted-foreground">
                      {group.supplier_contact}
                    </span>
                  ) : null}
                  <Badge variant="secondary">
                    дефицит: {group.total_deficit}
                  </Badge>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Позиция</TableHead>
                      <TableHead>Дефицит</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {group.lines.map((line) => (
                      <TableRow key={line.item_id}>
                        <TableCell className="font-medium">
                          {line.item_name}
                        </TableCell>
                        <TableCell>{line.deficit}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      {openSection === "inventory" ? (
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
                onChange={(e) =>
                  setCountForm({ ...countForm, scope_item_id: e.target.value })
                }
              />
              <Input
                placeholder="Локация (опц.)"
                value={countForm.scope_location}
                onChange={(e) =>
                  setCountForm({ ...countForm, scope_location: e.target.value })
                }
              />
              <Input
                placeholder="Заметка (опц.)"
                value={countForm.note}
                onChange={(e) =>
                  setCountForm({ ...countForm, note: e.target.value })
                }
              />
              <Button onClick={createCount} disabled={submitting}>
                Создать
              </Button>
            </div>

            {counts.length === 0 ? (
              <EmptyState
                title="Нет инвентаризаций"
                description="Создайте срез для сверки факта."
              />
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
                        <Badge
                          variant={
                            c.status === "applied" ? "secondary" : "outline"
                          }
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{c.note || "—"}</TableCell>
                      <TableCell>{c.line_count}</TableCell>
                      <TableCell>{c.counted_count}</TableCell>
                      <TableCell>{formatDate(c.created_at) || "—"}</TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          onClick={() => openCount(c.id)}
                        >
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
                  <Badge variant="secondary">
                    расхождений: {activeCount.diff_count}
                  </Badge>
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
                        <TableCell className="font-medium">
                          {line.batch_no}
                        </TableCell>
                        <TableCell>{line.location || "—"}</TableCell>
                        <TableCell>{line.system_qty}</TableCell>
                        <TableCell>{line.on_hand}</TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            min={0}
                            aria-label={`Факт ${line.batch_no}`}
                            value={countedInputs[line.id] ?? ""}
                            disabled={activeCount.status !== "draft"}
                            onChange={(e) =>
                              setCountedInputs({
                                ...countedInputs,
                                [line.id]: e.target.value,
                              })
                            }
                          />
                        </TableCell>
                        <TableCell>
                          {line.delta === null ? "—" : line.delta}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {activeCount.status === "draft" ? (
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={saveCounts}
                      disabled={submitting}
                    >
                      Сохранить факт
                    </Button>
                    <Button onClick={applyActiveCount} disabled={submitting}>
                      Применить
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={cancelActiveCount}
                      disabled={submitting}
                    >
                      Отменить
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      {openSection === "budget" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              Бюджет безопасности
              <Badge variant="secondary">{budgets.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 md:grid-cols-5">
              <Input
                aria-label="Название"
                placeholder="Название"
                value={budgetForm.name}
                onChange={(e) =>
                  setBudgetForm((f) => ({ ...f, name: e.target.value }))
                }
              />
              <Input
                aria-label="Начало периода"
                type="date"
                value={budgetForm.period_start}
                onChange={(e) =>
                  setBudgetForm((f) => ({ ...f, period_start: e.target.value }))
                }
              />
              <Input
                aria-label="Конец периода"
                type="date"
                value={budgetForm.period_end}
                onChange={(e) =>
                  setBudgetForm((f) => ({ ...f, period_end: e.target.value }))
                }
              />
              <Input
                aria-label="Плановая сумма"
                type="number"
                min={0}
                step="0.01"
                placeholder="Плановая сумма"
                value={budgetForm.planned_amount}
                onChange={(e) =>
                  setBudgetForm((f) => ({
                    ...f,
                    planned_amount: e.target.value,
                  }))
                }
              />
              <Input
                aria-label="Заметки"
                placeholder="Заметки (опц.)"
                value={budgetForm.notes}
                onChange={(e) =>
                  setBudgetForm((f) => ({ ...f, notes: e.target.value }))
                }
              />
            </div>
            <Button
              onClick={submitBudget}
              disabled={
                submitting ||
                !budgetForm.name.trim() ||
                !budgetForm.period_start ||
                !budgetForm.period_end
              }
            >
              Создать бюджет
            </Button>
            {budgets.length === 0 ? (
              <EmptyState
                title="Бюджетов нет"
                description="Создайте бюджет безопасности для контроля затрат на СИЗ."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Название</TableHead>
                    <TableHead>Период</TableHead>
                    <TableHead>План</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {budgets.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="font-medium">{b.name}</TableCell>
                      <TableCell>
                        {b.period_start} – {b.period_end}
                      </TableCell>
                      <TableCell>План: {b.planned_amount}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          onClick={() => void openBudget(b.id)}
                        >
                          Открыть
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}

            {activeBudget ? (
              <div className="space-y-2 border-t pt-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{activeBudget.name}</span>
                  <Badge variant="secondary">
                    Факт: {activeBudget.actual_total}
                  </Badge>
                  <Badge variant="outline">
                    Остаток: {activeBudget.remaining}
                  </Badge>
                </div>
                {activeBudget.by_category.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {activeBudget.by_category.map((c) => (
                      <li key={c.category}>
                        {c.category}: {c.amount}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {activeBudget.unpriced_receipt_count > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Приходов без цены: {activeBudget.unpriced_receipt_count}
                  </p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};

export default WarehousePage;
