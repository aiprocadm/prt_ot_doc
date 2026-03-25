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
    initialData: {
      tenancy: { tenant: { id: "", slug: "" } },
      outbox: [],
      webhooks: [],
      apiTokens: [],
      auditItems: [],
      integrationReadiness: null,
      attention: null,
      taskInbox: null,
      providerStatus: null,
      tenantHealth: null,
      roleSummary: null
    },
    errorMessage: "Не удалось загрузить операционную админ-консоль"
  });

  const providerSummary = data.integrationReadiness?.summary;
  const attentionSummary = data.attention?.summary;

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
          { label: "API tokens", value: data.apiTokens.length },
          { label: "Stub/mock providers", value: providerSummary?.non_production_total ?? "—" },
          { label: "Readiness blockers", value: attentionSummary?.readiness_blockers ?? "—" }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка админ-консоли" /> : null}
      {!loading && !error ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="text-base">Tenant health score</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.tenantHealth ? (
                <>
                  <p>Score: {data.tenantHealth.score} / 100</p>
                  <p>Grade: {data.tenantHealth.grade}</p>
                  <p>Failed jobs (24h): {data.tenantHealth.failed_jobs_last24h}</p>
                  <p>Poisoned events: {data.tenantHealth.outbox_events_poisoned}</p>
                </>
              ) : (
                <p className="text-muted-foreground">Health score временно недоступен</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Provider status</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.providerStatus ? (
                <>
                  <p>Production ready: {data.providerStatus.production_ready ? "yes" : "no"}</p>
                  <p>Blocking providers: {data.providerStatus.blocking_for_golive.length}</p>
                  {data.providerStatus.providers.slice(0, 3).map((provider) => <p key={provider.name}>{provider.name} · {provider.mode} · {provider.adapter}</p>)}
                </>
              ) : (
                <p className="text-muted-foreground">Provider status временно недоступен</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Role projection</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.roleSummary ? (
                <>
                  <p>Role: {data.roleSummary.role}</p>
                  <p>Open tasks: {data.roleSummary.open_tasks}</p>
                  <p>Overdue tasks: {data.roleSummary.overdue_tasks}</p>
                  <p>Overdue deadlines: {data.roleSummary.overdue_deadlines}</p>
                </>
              ) : (
                <p className="text-muted-foreground">Role summary временно недоступен</p>
              )}
            </CardContent>
          </Card>
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
            <CardContent className="space-y-2 text-sm">
              {data.auditItems.length ? data.auditItems.slice(0, 5).map((item) => <p key={item.id}>{item.action} · {item.object_type}</p>) : <p className="text-muted-foreground">События аудита отсутствуют</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Integration readiness</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.integrationReadiness ? (
                <>
                  <p>Configured: {data.integrationReadiness.summary.configured_total}</p>
                  <p>Production-ready: {data.integrationReadiness.summary.production_ready_total}</p>
                  <p>Stub/mock/disabled: {data.integrationReadiness.summary.non_production_total}</p>
                  <p>Delivery failed: {data.integrationReadiness.webhooks.delivery_failed_total}</p>
                </>
              ) : (
                <p className="text-muted-foreground">Readiness snapshot временно недоступен</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Attention center</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.attention ? (
                <>
                  <p>Overdue tasks: {data.attention.summary.overdue_tasks}</p>
                  <p>Due soon: {data.attention.summary.due_soon_tasks}</p>
                  <p>Overdue deadlines: {data.attention.summary.overdue_deadlines}</p>
                  <p>Readiness blockers: {data.attention.summary.readiness_blockers}</p>
                  {(data.attention.recommendations || []).slice(0, 2).map((item) => <p key={item}>{item}</p>)}
                </>
              ) : (
                <p className="text-muted-foreground">Attention snapshot временно недоступен</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Task inbox</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.taskInbox ? (
                <>
                  <p>Total open: {data.taskInbox.total}</p>
                  <p>Overdue: {data.taskInbox.overdue}</p>
                  {data.taskInbox.items.slice(0, 3).map((item) => <p key={item.id}>{item.title} · {item.priority} · {item.overdue ? "overdue" : "open"}</p>)}
                </>
              ) : (
                <p className="text-muted-foreground">Task inbox snapshot временно недоступен</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
};

export default AdminPage;
