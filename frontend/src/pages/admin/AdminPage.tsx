import { useCallback } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useAsyncResource } from "@/hooks/useAsyncResource";

const AdminPage = () => {
  const { can } = useAbility();
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getAdminSnapshot(), []),
    initialData: { tenancy: { tenant: { id: "", slug: "" } }, outbox: [], webhooks: [], apiTokens: [], auditItems: [] },
    errorMessage: "Не удалось загрузить операционную админ-консоль"
  });

  if (!can(PERMISSIONS.ADMIN_MANAGE_ROLES)) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Администрирование"
        description="Страница превращена из навигационного хаба в operational console по tenant health, outbox, webhooks, tokens и audit trail."
        actions={
          <>
            <Button variant="outline" asChild><Link to="/audit">Журнал аудита</Link></Button>
            <Button variant="outline" asChild><Link to="/integrations">Интеграции</Link></Button>
          </>
        }
        stats={[
          { label: "Tenant", value: data.tenancy.tenant.slug || "—" },
          { label: "Outbox", value: data.outbox.length },
          { label: "Webhooks", value: data.webhooks.length },
          { label: "API tokens", value: data.apiTokens.length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка админ-консоли" /> : null}
      {!loading && !error ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="text-base">Outbox</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">{data.outbox.slice(0, 5).map((item) => <p key={item.id}>{item.event_type} · {item.status} · attempts {item.attempts}</p>)}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Webhook endpoints</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">{data.webhooks.slice(0, 5).map((item) => <p key={item.id}>{item.code || item.id} · {item.is_active ? "active" : "disabled"}</p>)}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Audit feed</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">{data.auditItems.slice(0, 5).map((item) => <p key={item.id}>{item.action} · {item.object_type}</p>)}</CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
};

export default AdminPage;
