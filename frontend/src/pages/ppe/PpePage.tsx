import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { opsApi, type PpeIssueDto, type PpeItemDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PERMISSIONS } from "@/permissions/permissions";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { PersonDto } from "@/types/dto/persons";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const PpePage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [issues, setIssues] = useState<PpeIssueDto[]>([]);
  const [items, setItems] = useState<PpeItemDto[]>([]);
  const [persons, setPersons] = useState<PersonDto[]>([]);
  const [showQuickIssue, setShowQuickIssue] = useState(false);
  const [quickPersonId, setQuickPersonId] = useState("");
  const [quickItemId, setQuickItemId] = useState("");
  const [quickQty, setQuickQty] = useState(1);
  const [quickSubmitting, setQuickSubmitting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | "overdue" | "ready" | "draft">(
    searchParams.get("status") === "overdue" || searchParams.get("status") === "ready" || searchParams.get("status") === "draft"
      ? (searchParams.get("status") as "overdue" | "ready" | "draft")
      : "all"
  );

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await opsApi.getPpeOverview();
      setIssues(snapshot.issues);
      setItems(snapshot.items);
      setPersons(snapshot.persons);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить карточки выдачи СИЗ" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const personMap = useMemo(() => new Map(persons.map((person) => [person.id, person])), [persons]);
  const itemMap = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);

  const rows = useMemo(() => {
    const grouped = new Map<string, PpeIssueDto[]>();
    issues.forEach((issue) => {
      grouped.set(issue.person_id, [...(grouped.get(issue.person_id) ?? []), issue]);
    });

    return Array.from(grouped.entries()).map(([personId, personIssues]) => {
      const person = personMap.get(personId);
      const activeIssues = personIssues.filter((issue) => issue.status === "issued");
      const nextExpiry = activeIssues.map((issue) => issue.expires_at).filter(Boolean).sort()[0] ?? null;
      const itemLabels = activeIssues.map((issue) => itemMap.get(issue.item_id)?.name ?? issue.item_id).slice(0, 3);
      return {
        personId,
        employee: person?.full_name ?? personId,
        role: person?.position ?? "—",
        issued: `${activeIssues.length}/${personIssues.length}`,
        due: nextExpiry,
        items: itemLabels.join(", "),
        status: activeIssues.some((issue) => issue.expires_at && new Date(issue.expires_at) < new Date()) ? "overdue" : activeIssues.length === 0 ? "draft" : "ready"
      };
    });
  }, [issues, itemMap, personMap]);

  const visibleRows = useMemo(() => {
    if (statusFilter === "all") return rows;
    return rows.filter((row) => row.status === statusFilter);
  }, [rows, statusFilter]);

  const handleQuickIssue = async () => {
    if (!quickPersonId || !quickItemId) {
      toast.error("Выберите сотрудника и позицию СИЗ");
      return;
    }
    setQuickSubmitting(true);
    try {
      await opsApi.createPpeIssue({
        person_id: quickPersonId,
        item_id: quickItemId,
        quantity: Math.max(1, Number(quickQty) || 1),
      });
      toast.success("Выдача СИЗ создана");
      setShowQuickIssue(false);
      setQuickPersonId("");
      setQuickItemId("");
      setQuickQty(1);
      await load();
    } catch (err) {
      const next = err as ApiError;
      toast.error(next?.message || "Не удалось выполнить выдачу СИЗ");
    } finally {
      setQuickSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "СИЗ и склады" }]} />
        <div className="flex gap-2">
          <select
            className="h-10 rounded-md border px-3 text-sm"
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value as "all" | "overdue" | "ready" | "draft";
              setStatusFilter(next);
              const params = new URLSearchParams(searchParams);
              if (next === "all") params.delete("status");
              else params.set("status", next);
              setSearchParams(params, { replace: true });
            }}
            aria-label="Фильтр карточек СИЗ"
          >
            <option value="all">Все карточки</option>
            <option value="overdue">Требуют замены</option>
            <option value="ready">Актуальные</option>
            <option value="draft">Без активных выдач</option>
          </select>
          <Can permission={PERMISSIONS.PPE_ISSUE}>
            <Button variant="outline" onClick={() => navigate("/ppe/issue")}>
              Мобильная выдача
            </Button>
          </Can>
          <Can
            permission={PERMISSIONS.PPE_ISSUE}
            fallback={<Button disabled title="Недостаточно прав для выдачи СИЗ">Быстрая выдача</Button>}
          >
            <Button onClick={() => setShowQuickIssue((prev) => !prev)}>
              {showQuickIssue ? "Скрыть форму выдачи" : "Быстрая выдача"}
            </Button>
          </Can>
          <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
        </div>
      </div>
      {showQuickIssue ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Быстрая выдача СИЗ</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-4">
            <select
              className="h-10 rounded-md border px-3 text-sm"
              value={quickPersonId}
              onChange={(event) => setQuickPersonId(event.target.value)}
              aria-label="Сотрудник для выдачи СИЗ"
            >
              <option value="">Выберите сотрудника</option>
              {persons.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border px-3 text-sm"
              value={quickItemId}
              onChange={(event) => setQuickItemId(event.target.value)}
              aria-label="Позиция СИЗ"
            >
              <option value="">Выберите СИЗ</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={1}
              className="h-10 rounded-md border px-3 text-sm"
              value={quickQty}
              onChange={(event) => setQuickQty(Number(event.target.value) || 1)}
              aria-label="Количество СИЗ"
            />
            <Button onClick={() => void handleQuickIssue()} disabled={quickSubmitting}>
              {quickSubmitting ? "Выдача..." : "Выдать СИЗ"}
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Карточки сотрудников</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted-foreground">{loading ? "Загрузка…" : `${visibleRows.length} сотрудников по текущему фильтру.`}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Активные выдачи</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted-foreground">{loading ? "Загрузка…" : `${issues.filter((issue) => issue.status === "issued").length} активных выдач.`}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Требуют замены</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted-foreground">{loading ? "Загрузка…" : `${rows.filter((row) => row.status === "overdue").length} сотрудников с просрочкой.`}</CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Карточки выдачи СИЗ</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка карточек СИЗ" /> : null}
          {!loading && !error && visibleRows.length === 0 ? (
            <EmptyState title="Нет данных по выдаче" description="В этом тенанте пока не зарегистрированы выдачи СИЗ." />
          ) : null}
          {!loading && !error && visibleRows.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Сотрудник</TableHead>
                  <TableHead>Должность</TableHead>
                  <TableHead>Выдано</TableHead>
                  <TableHead>Ближайшая замена</TableHead>
                  <TableHead>Статус карточки</TableHead>
                  <TableHead>Позиции</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleRows.map((row) => (
                  <TableRow key={row.personId}>
                    <TableCell className="font-medium">{row.employee}</TableCell>
                    <TableCell>{row.role}</TableCell>
                    <TableCell>{row.issued}</TableCell>
                    <TableCell>{formatDate(row.due) || "—"}</TableCell>
                    <TableCell>
                      {row.status === "overdue" ? "Требует замены" : row.status === "ready" ? "Актуально" : "Нет активных выдач"}
                    </TableCell>
                    <TableCell>{row.items || "—"}</TableCell>
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

export default PpePage;
