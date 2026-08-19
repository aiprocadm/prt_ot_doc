import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  MANAGED_CLIENTS_DISABLED,
  managedClientsApi,
  type ClientAuditReportPage,
  type ManagedClient,
  type ManagedClientMode,
} from "@/api/managedClients";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { lightLabel, lightVariant } from "@/pages/managed-clients/lights";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

/**
 * Карточка клиента (BIZ-51 срез-10): отчёты авто-аудита нашли экран.
 *
 * Кокпит заполнен до предела (6 блоков из 6 — срез-6), поэтому отчёты живут
 * в отдельной карточке, куда ведёт имя клиента из портфеля.
 */

const MODE_LABELS: Record<ManagedClientMode, string> = {
  lightweight: "В нашем контуре",
  dedicated: "Свой контур",
};

const CONTRACT_LABELS: Record<string, string> = {
  draft: "Черновик",
  active: "Действует",
  suspended: "Приостановлен",
  terminated: "Расторгнут",
};

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const isModuleDisabled = (err: unknown): boolean =>
  Boolean(
    err &&
      typeof err === "object" &&
      (err as ApiError).code === MANAGED_CLIENTS_DISABLED,
  );

const ClientCardPage = () => {
  const { clientId = "" } = useParams();
  const [client, setClient] = useState<ManagedClient | null>(null);
  const [reports, setReports] = useState<ClientAuditReportPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [moduleDisabled, setModuleDisabled] = useState(false);
  const [running, setRunning] = useState(false);
  // Настройка адреса скрыта до клика: два всегда видимых поля съели бы бюджет
  // экрана, а сама настройка нужна раз в жизни клиента.
  const [editingEmail, setEditingEmail] = useState(false);
  const [email, setEmail] = useState("");
  const [optIn, setOptIn] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [sendResult, setSendResult] = useState<string | null>(null);
  const [runSummary, setRunSummary] = useState<string | null>(null);
  const [runError, setRunError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError(null);
    setModuleDisabled(false);
    try {
      const [clientData, reportsData] = await Promise.all([
        managedClientsApi.get(clientId),
        managedClientsApi.auditReports(clientId),
      ]);
      setClient(clientData);
      setReports(reportsData);
      setEmail(clientData.report_email ?? "");
      setOptIn(Boolean(clientData.report_opt_in));
    } catch (err) {
      if (isModuleDisabled(err)) {
        setModuleDisabled(true);
      } else {
        setError(asApiError(err, "Не удалось загрузить карточку клиента"));
      }
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
  }, [load]);

  const runNow = async () => {
    setRunning(true);
    setRunSummary(null);
    setRunError(null);
    try {
      const result = await managedClientsApi.runAudit();
      // Итог остаётся на экране, не в тосте: специалист читает слагаемые
      // («уже есть за сегодня», «пропущено») после того, как тост погас бы.
      setRunSummary(result.summary);
      await load();
    } catch (err) {
      setRunError(asApiError(err, "Не удалось собрать отчёт"));
    } finally {
      setRunning(false);
    }
  };

  const saveEmail = async () => {
    setSavingEmail(true);
    try {
      await managedClientsApi.update(clientId, {
        // Пусто → null: пустая строка означала бы «адрес есть, но пустой».
        report_email: email.trim() || null,
        report_opt_in: optIn,
      });
      setEditingEmail(false);
      await load();
    } catch (err) {
      setError(asApiError(err, "Не удалось сохранить адрес"));
    } finally {
      setSavingEmail(false);
    }
  };

  const sendReport = async (reportId: string) => {
    setSendResult(null);
    try {
      const result = await managedClientsApi.sendReport(clientId, reportId);
      // Причина остаётся на экране: «не отправлено» без объяснения одинаково
      // выглядит и когда нет согласия, и когда не настроена почта.
      setSendResult(result.reason);
    } catch (err) {
      setSendResult(
        asApiError(err, "Не удалось отправить отчёт").message ?? "Ошибка",
      );
    }
  };

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title={client?.name ?? "Карточка клиента"}
        description="Отчёты авто-аудита: что изменилось, что просрочено, что нужно сделать."
      />
      <div>
        <Link
          to="/managed-clients"
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
        >
          ← К списку клиентов
        </Link>
      </div>

      {moduleDisabled ? (
        <EmptyState
          title="Модуль не подключён"
          description="Ведение клиентов доступно на тарифе с модулем «Ведение клиентов (аутсорсинг)»."
        />
      ) : (
        <>
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка карточки" /> : null}

          {!loading && !error && client ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">О клиенте</CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  className="flex flex-wrap gap-4 text-sm"
                  data-testid="client-info"
                >
                  <span>
                    Режим:{" "}
                    <strong>{MODE_LABELS[client.mode] ?? client.mode}</strong>
                  </span>
                  <span>
                    Договор:{" "}
                    <strong>
                      {CONTRACT_LABELS[client.contract_status] ??
                        client.contract_status}
                    </strong>
                    {client.contract_no ? ` (${client.contract_no})` : null}
                  </span>
                  {client.contract_ends_at ? (
                    <span>
                      Действует до:{" "}
                      <strong>{formatDate(client.contract_ends_at)}</strong>
                    </span>
                  ) : null}
                  <span data-testid="report-email-state">
                    Отчёты:{" "}
                    <strong>
                      {client.report_email
                        ? client.report_opt_in
                          ? client.report_email
                          : `${client.report_email} (согласия нет)`
                        : "адрес не указан"}
                    </strong>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingEmail((v) => !v)}
                    data-testid="edit-report-email"
                  >
                    {editingEmail ? "Отмена" : "Настроить отчёты"}
                  </Button>
                </div>

                {editingEmail ? (
                  <form
                    className="mt-3 flex flex-wrap items-end gap-2"
                    data-testid="report-email-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void saveEmail();
                    }}
                  >
                    <div className="flex-1 min-w-[220px] space-y-1">
                      <label
                        className="text-xs text-muted-foreground"
                        htmlFor="report-email"
                      >
                        Адрес клиента для отчётов
                      </label>
                      <Input
                        id="report-email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="client@example.com"
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={optIn}
                        onChange={(e) => setOptIn(e.target.checked)}
                        data-testid="report-opt-in"
                      />
                      {/* Согласие — отдельное условие: знать адрес и иметь
                          право писать на него это разные вещи. */}
                      Клиент согласен получать отчёты
                    </label>
                    <Button
                      type="submit"
                      variant="outline"
                      size="sm"
                      disabled={savingEmail}
                    >
                      Сохранить
                    </Button>
                  </form>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {!loading && !error ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">
                    Отчёты авто-аудита
                  </CardTitle>
                  {/* Вторичная кнопка: «раз в неделю» проверяемо человеком,
                      а не предметом веры (правило среза-7). */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void runNow()}
                    disabled={running}
                    data-testid="run-audit-button"
                  >
                    {running ? "Собираем…" : "Собрать отчёт сейчас"}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {runSummary ? (
                  <p className="text-sm" data-testid="run-audit-result">
                    {runSummary}
                  </p>
                ) : null}
                <ErrorState error={runError ?? undefined} onRetry={runNow} />
                {sendResult ? (
                  <p className="text-sm" data-testid="send-report-result">
                    {sendResult}
                  </p>
                ) : null}

                {reports && reports.items.length === 0 ? (
                  <EmptyState
                    title="Отчётов пока нет"
                    description="Авто-аудит идёт еженедельно (понедельник); первый отчёт можно собрать кнопкой выше."
                  />
                ) : null}
                {reports && reports.items.length > 0 ? (
                  <ul className="space-y-3">
                    {reports.items.map((report) => (
                      <li
                        key={report.id}
                        className="space-y-1 rounded-md border border-border p-3"
                        data-testid="audit-report-row"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">
                            {formatDate(report.period_start)} —{" "}
                            {formatDate(report.period_end)}
                          </span>
                          <Badge variant={lightVariant(report.overall)}>
                            {lightLabel(report.overall)}
                          </Badge>
                        </div>
                        {/* Текст отчёта целиком: «что изменилось, что
                            просрочено, что нужно сделать» — смысл аудита. */}
                        <p className="text-sm text-muted-foreground">
                          {report.summary}
                        </p>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void sendReport(report.id)}
                          data-testid="send-report"
                        >
                          Отправить клиенту
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
};

export default ClientCardPage;
