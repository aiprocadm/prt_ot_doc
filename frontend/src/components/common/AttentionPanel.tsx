import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Info,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  workspaceApi,
  type DisciplineAttention,
  type ReadinessBlocker,
  type WorkspaceAttentionDto,
} from "@/api/workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  blockerActionLabel,
  blockerActionPath,
} from "@/utils/workspaceNavigation";

const blockerLink = (blocker: ReadinessBlocker) =>
  blockerActionPath(blocker.code, blocker.entity_type);

/** Название дисциплины берём из ответа сервера: вторая правда о названиях
 *  разошлась бы с бэкендом (там словарь один на продукт). */
const disciplineTitle = (
  code: string,
  disciplines: DisciplineAttention[],
): string => disciplines.find((d) => d.code === code)?.title ?? code;

const severityIcon = (severity: string) => {
  if (severity === "critical")
    return <AlertCircle className="h-4 w-4 text-destructive shrink-0" />;
  if (severity === "high")
    return <AlertTriangle className="h-4 w-4 text-orange-500 shrink-0" />;
  return <Info className="h-4 w-4 text-muted-foreground shrink-0" />;
};

const severityVariant = (
  s: string,
): "default" | "secondary" | "destructive" => {
  if (s === "critical") return "destructive";
  if (s === "high") return "secondary";
  return "default";
};

interface BlockerRowProps {
  blocker: ReadinessBlocker;
}

const BlockerRow = ({ blocker }: BlockerRowProps) => {
  const href = blockerLink(blocker);
  const actionLabel = blockerActionLabel(blocker.code);
  return (
    <div className="flex items-start gap-3 rounded-md border bg-muted/30 p-3">
      {severityIcon(blocker.severity)}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{blocker.title}</span>
          <Badge
            variant={severityVariant(blocker.severity)}
            className="text-xs"
          >
            {blocker.count} шт.
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{blocker.reason}</p>
        <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">
          {blocker.action_hint}
        </p>
        <Link
          to={href}
          className="mt-2 inline-flex text-xs font-medium text-blue-600 hover:underline"
        >
          {actionLabel}
        </Link>
      </div>
      <Button
        asChild
        size="sm"
        variant="ghost"
        className="shrink-0"
        aria-label={`Перейти: ${actionLabel}`}
      >
        <Link to={href}>
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </Button>
    </div>
  );
};

interface AttentionPanelProps {
  /** На странице «Центр внимания» заголовок уже есть снаружи — дублировать не нужно. */
  showOuterTitle?: boolean;
}

export const AttentionPanel = ({
  showOuterTitle = true,
}: AttentionPanelProps) => {
  const [data, setData] = useState<WorkspaceAttentionDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    workspaceApi
      .getAttention(20)
      .then(setData)
      .catch(() => setError("Не удалось загрузить центр внимания"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Поля необязательные: старый ответ (и моки прежних тестов) их не содержат.
  const disciplines = data?.disciplines ?? [];
  const items = data?.items ?? [];
  const s = data?.summary;
  const totalCritical =
    (s?.overdue_tasks ?? 0) +
    (s?.overdue_deadlines ?? 0) +
    (s?.failed_sync_batches ?? 0);
  const allClear =
    !loading && !error && totalCritical === 0 && !data?.blockers.length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div
          className={
            showOuterTitle
              ? "flex items-center justify-between"
              : "flex items-center justify-end gap-2"
          }
        >
          {showOuterTitle ? (
            <CardTitle className="text-base flex items-center gap-2">
              {allClear ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : (
                <AlertCircle className="h-4 w-4 text-destructive" />
              )}
              Центр внимания
            </CardTitle>
          ) : null}
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {/* Summary bar */}
        {s && (
          <div className="flex flex-wrap gap-3 text-sm">
            {s.overdue_tasks > 0 && (
              <Link
                to="/tasks?overdue=true"
                className="flex items-center gap-1 text-destructive hover:underline"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                {s.overdue_tasks} просроченных задач
              </Link>
            )}
            {s.due_soon_tasks > 0 && (
              <Link
                to="/tasks"
                className="flex items-center gap-1 text-orange-500 hover:underline"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                {s.due_soon_tasks} задач — срок скоро
              </Link>
            )}
            {s.overdue_deadlines > 0 && (
              <Link
                to="/tasks?overdue=true"
                className="flex items-center gap-1 text-destructive hover:underline"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                {s.overdue_deadlines} просроченных обязательств
              </Link>
            )}
            {s.failed_sync_batches > 0 && (
              <span className="flex items-center gap-1 text-destructive">
                <AlertCircle className="h-3.5 w-3.5" />
                {s.failed_sync_batches} ошибок offline-синхронизации
              </span>
            )}
            {s.pending_sync_batches > 0 && (
              <span className="flex items-center gap-1 text-muted-foreground">
                <Info className="h-3.5 w-3.5" />
                {s.pending_sync_batches} ожидающих синхронизаций
              </span>
            )}
            {allClear && (
              <span className="flex items-center gap-1.5 text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Нет критичных нарушений
              </span>
            )}
          </div>
        )}

        {/* Дисциплины (BIZ-54-57 срез-1, разд. 57.2). Полоса внутри
            существующей карточки: новый блок верхнего уровня покрасил бы
            приёмку UX-бюджета на дашборде (BIZ-60). */}
        {disciplines.length > 0 && (
          <div className="space-y-1" data-testid="attention-disciplines">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              По дисциплинам
            </p>
            <div className="flex flex-wrap gap-2 text-xs">
              {disciplines.map((d) => (
                <span
                  key={d.code}
                  data-testid="attention-discipline"
                  title={d.reason ?? undefined}
                  className={
                    d.measured
                      ? "rounded-md border px-2 py-1"
                      : "rounded-md border border-dashed px-2 py-1 text-muted-foreground"
                  }
                >
                  {d.title}:{" "}
                  {d.measured ? (
                    <strong
                      className={d.overdue > 0 ? "text-destructive" : undefined}
                    >
                      {d.overdue > 0
                        ? `просрочено ${d.overdue}`
                        : d.due_soon > 0
                          ? `срок скоро ${d.due_soon}`
                          : "нарушений нет"}
                    </strong>
                  ) : (
                    /* Не «ноль», а честное «не считаем»: ноль читался бы как
                       благополучие там, где данных нет вовсе. */
                    "учёт не ведётся"
                  )}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Записи внимания. До BIZ-54-57 среза-1 массив items приходил с
            сервера и НЕ рисовался ни одним экраном — сервер считал список,
            который выбрасывался. */}
        {items.length > 0 && (
          <div className="space-y-2" data-testid="attention-items">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Требует внимания ({items.length})
              {data?.items_truncated ? (
                /* Обрезанный список обязан назвать себя обрезанным: молча
                   усечённый читается как полный. */
                <span className="ml-2 normal-case font-normal">
                  — показаны не все
                </span>
              ) : null}
            </p>
            <ul className="space-y-1">
              {items.map((item) => (
                <li
                  key={`${item.item_type}:${item.id}`}
                  data-testid="attention-item"
                  className="flex items-start gap-2 text-sm"
                >
                  {severityIcon(item.severity)}
                  <span className="flex-1 min-w-0">
                    <span className="font-medium">{item.title}</span>{" "}
                    <span className="text-muted-foreground">
                      — {item.reason}
                    </span>
                  </span>
                  {item.discipline ? (
                    <Badge variant="outline" className="text-xs shrink-0">
                      {disciplineTitle(item.discipline, disciplines)}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Readiness blockers */}
        {data && data.blockers.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Блокеры готовности ({data.blockers.length})
            </p>
            {data.blockers.map((b) => (
              <BlockerRow key={b.code} blocker={b} />
            ))}
          </div>
        )}

        {/* Recommendations */}
        {data && data.recommendations.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Рекомендуемые действия
            </p>
            <ul className="space-y-1">
              {data.recommendations.map((rec, i) => (
                <li
                  key={i}
                  className="text-xs text-muted-foreground flex gap-2"
                >
                  <ArrowRight className="h-3 w-3 mt-0.5 shrink-0 text-blue-500" />
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}

        {loading && !data && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}
      </CardContent>
    </Card>
  );
};
