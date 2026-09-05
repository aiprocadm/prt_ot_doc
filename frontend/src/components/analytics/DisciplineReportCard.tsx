import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { analyticsApi } from "@/api/analyticsApi";
import { UNMARKED_DISCIPLINE_FILTER } from "@/api/incidents";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type { DisciplineReportPageDto } from "@/types/dto/analytics";
import type { ApiError } from "@/types/dto/common";

/**
 * Авто-отчёт о состоянии по дисциплинам (Доп. №1 разд. 57.4).
 *
 * Отчёт — запись на дату, а не пересчёт: разрез «по дисциплинам» выше
 * говорит про «сейчас», отчёт — «что было в прошлый раз и куда движемся».
 * Пишется еженедельным тиком; «Собрать сейчас» — тот же прогон руками,
 * за день отчёт один, второго не появится.
 */

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

// Дата отчёта приходит как YYYY-MM-DD; часового пояса у неё нет, и
// пропускать её через Date значило бы сдвинуть день на границе суток.
const formatDay = (iso: string): string => {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
};

const formatDelta = (delta: number | null): string => {
  if (delta === null) return "—";
  if (delta > 0) return `+${delta}`;
  if (delta < 0) return String(delta);
  return "0";
};

const EMPTY: DisciplineReportPageDto = { items: [], total: 0 };

export function DisciplineReportCard() {
  const reportsRes = useAsyncResource<DisciplineReportPageDto>({
    loader: useCallback(() => analyticsApi.listDisciplineReports(12), []),
    initialData: EMPTY,
    errorMessage: "Не удалось загрузить отчёты о состоянии",
  });
  // 0 — самый свежий; листание «раньше/позже» без полей ввода.
  const [index, setIndex] = useState(0);
  const [running, setRunning] = useState(false);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [runError, setRunError] = useState<ApiError | null>(null);

  const reports = reportsRes.data.items;
  const report = reports[index] ?? reports[0];

  const runNow = async () => {
    setRunning(true);
    setRunNote(null);
    setRunError(null);
    try {
      const result = await analyticsApi.runDisciplineReport();
      // Итог остаётся на экране, а не в тосте: «уже есть за сегодня» — это
      // ответ, который надо прочитать, а не мигнувшее уведомление.
      setRunNote(result.summary);
      setIndex(0);
      await reportsRes.reload();
    } catch (err) {
      setRunError(asApiError(err, "Не удалось собрать отчёт"));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card data-testid="discipline-report-card">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Отчёт о состоянии по дисциплинам</CardTitle>
          <div className="flex flex-wrap gap-1">
            {reports.length > 1 ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={index >= reports.length - 1}
                  onClick={() =>
                    setIndex((i) => Math.min(i + 1, reports.length - 1))
                  }
                >
                  ← Раньше
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={index === 0}
                  onClick={() => setIndex((i) => Math.max(i - 1, 0))}
                >
                  Позже →
                </Button>
              </>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              disabled={running}
              onClick={runNow}
            >
              {running ? "Собираем…" : "Собрать сейчас"}
            </Button>
          </div>
        </div>
        <CardDescription>
          Снимок на дату, собирается автоматически раз в неделю. Числа — те же,
          что в разрезе «По дисциплинам»; «—» значит «не считается», а не ноль.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {runNote ? (
          <p
            className="text-sm text-muted-foreground"
            data-testid="discipline-report-run-note"
          >
            {runNote}
          </p>
        ) : null}
        <ErrorState error={runError} />
        {reportsRes.error ? (
          <ErrorState error={reportsRes.error} onRetry={reportsRes.reload} />
        ) : !report ? (
          <EmptyState
            title="Отчётов ещё нет"
            description="Первый соберётся в понедельник утром — или нажмите «Собрать сейчас»."
          />
        ) : (
          <>
            <p className="text-sm">
              <span className="font-medium">
                Отчёт за {formatDay(report.period_end)}
              </span>
              {report.payload.previous_period_end ? (
                <span className="text-muted-foreground">
                  {" "}
                  · сравнение с {formatDay(report.payload.previous_period_end)}
                </span>
              ) : null}
            </p>
            <p className="text-sm" data-testid="discipline-report-summary">
              {report.summary}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">Дисциплина</th>
                    <th className="py-2 pr-4">Происшествия</th>
                    <th className="py-2 pr-4">Просрочки</th>
                    <th className="py-2 pr-4">Всего</th>
                    <th className="py-2">К прошлому отчёту</th>
                  </tr>
                </thead>
                <tbody>
                  {report.payload.rows.map((row) => (
                    <tr key={row.discipline} className="border-b last:border-0">
                      <td className="py-2 pr-4">{row.title}</td>
                      <td className="py-2 pr-4">
                        {row.incidents_open > 0 ? (
                          <Link
                            to={`/incidents?discipline=${encodeURIComponent(row.discipline)}`}
                            className="text-primary underline"
                          >
                            {row.incidents_open}
                          </Link>
                        ) : (
                          row.incidents_open
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        {row.overdue_items === null ? (
                          <span
                            className="text-muted-foreground"
                            title="По этой дисциплине не считается"
                          >
                            —
                          </span>
                        ) : (
                          row.overdue_items
                        )}
                      </td>
                      <td className="py-2 pr-4">{row.total_issues}</td>
                      <td
                        className="py-2"
                        title={
                          row.delta === null
                            ? "В прошлом отчёте сравнить не с чем"
                            : undefined
                        }
                      >
                        {formatDelta(row.delta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {report.payload.unmarked_incidents > 0 ? (
              <p className="text-sm text-muted-foreground">
                Не размечено дисциплиной:{" "}
                <Link
                  to={`/incidents?discipline=${UNMARKED_DISCIPLINE_FILTER}`}
                  className="text-primary underline"
                >
                  {report.payload.unmarked_incidents}
                </Link>{" "}
                — ни один контур их не видит.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
