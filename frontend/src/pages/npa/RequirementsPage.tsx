import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { complianceRequirementsApi } from "@/api/complianceRequirements";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  RequirementEvidenceDialog,
  RequirementFormDialog,
  SEVERITY_LABELS,
} from "@/features/complianceRequirements/RequirementDialogs";
import { ROUTES } from "@/router/routes";
import { useNpaStore } from "@/stores/npa";
import type {
  ComplianceRequirementDto,
  ComplianceRequirementListDto,
  RequirementStatus,
} from "@/types/dto/complianceRequirements";
import type { ApiError } from "@/types/dto/common";

/**
 * Реестр требований — обязательное ядро арендатора (B.18 разд. 19.2, срез-145).
 *
 * До среза платформа знала, какие документы зависят от акта (связи НПА), но не
 * знала, какие обязанности из него следуют. Здесь они — строками: откуда,
 * кто отвечает, как часто, до какой даты, чем доказано.
 *
 * «Просрочено» и «дней осталось» приходят с сервера (UTC-«сегодня»): витрина
 * их не пересчитывает — вечером по Москве «сегодня» другое.
 */

const STATUS_LABELS: Record<RequirementStatus, string> = {
  active: "на контроле",
  fulfilled: "исполнено",
  retired: "снято с контроля",
};

const formatDay = (value?: string | null): string => {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return day && month && year ? `${day}.${month}.${year}` : value;
};

const periodicityLabel = (days?: number | null): string => {
  if (!days) return "разово";
  if (days % 365 === 0) {
    const years = days / 365;
    return years === 1 ? "ежегодно" : `раз в ${years} г.`;
  }
  if (days % 30 === 0) {
    const months = days / 30;
    return months === 1 ? "ежемесячно" : `раз в ${months} мес.`;
  }
  return `раз в ${days} дн.`;
};

/** Срок одной строкой: дата и сколько до неё (или на сколько просрочено). */
export const dueLabel = (item: ComplianceRequirementDto): string => {
  if (item.status !== "active") return STATUS_LABELS[item.status];
  if (!item.next_due_at) return "без срока";
  const day = formatDay(item.next_due_at);
  if (item.overdue) {
    return `${day} · просрочено на ${Math.abs(item.days_left ?? 0)} дн.`;
  }
  if (item.days_left === 0) return `${day} · сегодня`;
  return `${day} · через ${item.days_left ?? 0} дн.`;
};

const severityVariant = (
  severity: ComplianceRequirementDto["severity"],
): "default" | "secondary" | "destructive" | "outline" => {
  if (severity === "critical") return "destructive";
  if (severity === "high") return "default";
  if (severity === "medium") return "secondary";
  return "outline";
};

type StatusFilter = RequirementStatus | "";

const RequirementsPage = () => {
  const { list: loadActs, all: acts } = useNpaStore();
  const [searchParams] = useSearchParams();
  // Ссылка с экрана НПА ведёт сюда с `?npa_id=` — показываем требования акта.
  const npaFilter = searchParams.get("npa_id") ?? undefined;
  const [status, setStatus] = useState<StatusFilter>("");
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const [data, setData] = useState<ComplianceRequirementListDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    void complianceRequirementsApi
      .list({
        npa_id: npaFilter,
        status: status || undefined,
        overdue: onlyOverdue,
      })
      .then((response) => setData(response))
      .catch((failure: ApiError) => setError(failure))
      .finally(() => setLoading(false));
  }, [npaFilter, status, onlyOverdue]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    void loadActs();
  }, [loadActs]);

  const retire = async (item: ComplianceRequirementDto) => {
    try {
      await complianceRequirementsApi.retire(item.id);
      toast.success("Требование снято с контроля");
      load();
    } catch {
      toast.error("Не удалось снять требование с контроля");
    }
  };

  const items = data?.items ?? [];
  const canManage = data?.can_manage ?? false;
  const filteredAct = npaFilter
    ? acts.find((act) => act.id === npaFilter)
    : undefined;

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: ROUTES.DASHBOARD },
          { label: "НПА", to: "/npa" },
          { label: "Реестр требований" },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={load} />
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-6">
          <div className="flex flex-col gap-2">
            <label
              className="text-sm font-medium"
              htmlFor="requirements-status"
            >
              Статус
            </label>
            <select
              id="requirements-status"
              className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={status}
              onChange={(event) =>
                setStatus(event.target.value as StatusFilter)
              }
            >
              <option value="">все</option>
              <option value="active">на контроле</option>
              <option value="fulfilled">исполнено</option>
              <option value="retired">снято с контроля</option>
            </select>
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={onlyOverdue}
              onChange={(event) => setOnlyOverdue(event.target.checked)}
            />
            только просроченные
          </label>
          {data ? (
            <div
              className="pb-2 text-sm text-muted-foreground"
              data-testid="requirements-summary"
            >
              Всего: {data.total} · на контроле: {data.active} · просрочено:{" "}
              <span
                className={data.overdue > 0 ? "font-medium text-red-700" : ""}
              >
                {data.overdue}
              </span>
              {filteredAct ? (
                <>
                  {" "}
                  · акт{" "}
                  <Link
                    className="underline"
                    to={`/npa?selected=${filteredAct.id}`}
                  >
                    {filteredAct.code}
                  </Link>
                </>
              ) : null}
            </div>
          ) : null}
          {canManage ? (
            <RequirementFormDialog
              acts={acts}
              trigger={<Button className="ml-auto">Добавить требование</Button>}
              onCreated={load}
            />
          ) : null}
        </CardContent>
      </Card>
      {loading && !data ? (
        <LoadingScreen label="Загрузка реестра требований" />
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <EmptyState
          title="Требований нет"
          description={
            status || onlyOverdue || npaFilter
              ? "По этому отбору ничего не найдено — измените фильтры."
              : canManage
                ? "Заведите первое требование кнопкой «Добавить требование»: что арендатор обязан делать по НПА, как часто и кто отвечает."
                : "Реестр требований ведёт специалист по охране труда; за вами пока ничего не закреплено."
          }
        />
      ) : null}
      {items.length > 0 ? (
        <Card>
          <CardContent className="py-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Код</TableHead>
                  <TableHead>Требование</TableHead>
                  <TableHead>НПА</TableHead>
                  <TableHead>Срок</TableHead>
                  <TableHead>Периодичность</TableHead>
                  <TableHead>Ответственный</TableHead>
                  {canManage ? <TableHead>Действия</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow
                    key={item.id}
                    data-testid="requirement-row"
                    data-overdue={item.overdue ? "true" : "false"}
                  >
                    <TableCell className="font-medium">{item.code}</TableCell>
                    <TableCell>
                      <div>{item.title}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant={severityVariant(item.severity)}>
                          {SEVERITY_LABELS[item.severity]}
                        </Badge>
                        {item.evidence_count > 0
                          ? `доказательств: ${item.evidence_count}`
                          : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      {item.npa_id ? (
                        <Link
                          className="underline"
                          to={`/npa?selected=${item.npa_id}`}
                        >
                          {item.npa_code ?? item.npa_id}
                          {item.clause_code ? ` · ${item.clause_code}` : ""}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell
                      className={item.overdue ? "font-medium text-red-700" : ""}
                    >
                      {dueLabel(item)}
                    </TableCell>
                    <TableCell>
                      {periodicityLabel(item.periodicity_days)}
                    </TableCell>
                    <TableCell>{item.owner_name ?? "—"}</TableCell>
                    {canManage ? (
                      <TableCell>
                        {item.status === "active" ? (
                          <div className="flex items-center gap-1">
                            <RequirementEvidenceDialog
                              requirement={item}
                              trigger={
                                <Button variant="outline" size="sm">
                                  Исполнено
                                </Button>
                              }
                              onConfirmed={load}
                            />
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => void retire(item)}
                            >
                              Снять с контроля
                            </Button>
                          </div>
                        ) : null}
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};

export default RequirementsPage;
