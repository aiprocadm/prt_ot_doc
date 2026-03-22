import { useCallback } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";

const SettingsPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getSettingsSnapshot(), []),
    initialData: { tenancy: { tenant: { id: "", slug: "" } }, notifications: {}, apiTokens: [] },
    errorMessage: "Не удалось загрузить настройки tenant"
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Настройки tenant"
        description="Раздел больше не является заглушкой: он подтягивает tenant context, notification settings и API tokens."
        actions={<Button asChild variant="outline"><Link to="/admin">Администрирование</Link></Button>}
        stats={[
          { label: "Tenant", value: data.tenancy.tenant.slug || "—" },
          { label: "API токены", value: data.apiTokens.length },
          { label: "Correlation ID", value: data.tenancy.correlation_id || "—" }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка настроек" /> : null}
      {!loading && !error ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="text-base">Контур</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>Slug: <span className="font-medium">{data.tenancy.tenant.slug || "—"}</span></p>
              <p>Code: <span className="font-medium">{data.tenancy.tenant.code || "—"}</span></p>
              <p>Schema: <span className="font-medium">{data.tenancy.tenant.schema_name || "—"}</span></p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Квоты и usage</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>Параллельные jobs: <span className="font-medium">{data.tenancy.quota?.max_parallel_jobs ?? "—"}</span></p>
              <p>Лимит генераций/месяц: <span className="font-medium">{data.tenancy.quota?.max_doc_generations_per_month ?? "—"}</span></p>
              <p>Текущие генерации: <span className="font-medium">{data.tenancy.usage?.doc_generations ?? "—"}</span></p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Уведомления и доступ</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>Email: <span className="font-medium">{data.notifications.email_enabled ? "Включен" : "Выключен"}</span></p>
              <p>Telegram: <span className="font-medium">{data.notifications.telegram_enabled ? "Включен" : "Выключен"}</span></p>
              <p>Reminder window: <span className="font-medium">{data.notifications.reminder_window_days ?? "—"}</span></p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
};

export default SettingsPage;
