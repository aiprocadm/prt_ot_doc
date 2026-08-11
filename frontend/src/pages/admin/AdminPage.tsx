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
      roleSummary: null,
    },
    errorMessage: "Не удалось загрузить операционную админ-консоль",
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
        description="Операционная консоль: здоровье тенанта, исходящая очередь, вебхуки, токены и журнал аудита."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/audit">Журнал аудита</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/integrations">Интеграции</Link>
            </Button>
          </>
        }
        stats={[
          { label: "Тенант", value: data.tenancy.tenant.slug || "—" },
          { label: "Исходящая очередь", value: data.outbox.length },
          { label: "Вебхуки", value: data.webhooks.length },
          { label: "API-токены", value: data.apiTokens.length },
          {
            label: "Непродакшен-провайдеры",
            value: providerSummary?.non_production_total ?? "—",
          },
          {
            label: "Блокеры готовности",
            value: attentionSummary?.readiness_blockers ?? "—",
          },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка админ-консоли" /> : null}
      {!loading && !error ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Оценка здоровья тенанта
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.tenantHealth ? (
                <>
                  <p>Балл: {data.tenantHealth.score} / 100</p>
                  <p>Оценка: {data.tenantHealth.grade}</p>
                  <p>
                    Сбойных заданий (24 ч):{" "}
                    {data.tenantHealth.failed_jobs_last24h}
                  </p>
                  <p>
                    Отравленных событий:{" "}
                    {data.tenantHealth.outbox_events_poisoned}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">
                  Оценка здоровья временно недоступна
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Статус провайдеров</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.providerStatus ? (
                <>
                  <p>
                    Готовность к продакшену:{" "}
                    {data.providerStatus.production_ready ? "да" : "нет"}
                  </p>
                  <p>
                    Блокирующих провайдеров:{" "}
                    {data.providerStatus.blocking_for_golive.length}
                  </p>
                  {data.providerStatus.providers.slice(0, 3).map((provider) => (
                    <p key={provider.name}>
                      {provider.name} · {provider.mode} · {provider.adapter}
                    </p>
                  ))}
                </>
              ) : (
                <p className="text-muted-foreground">
                  Статус провайдеров временно недоступен
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Проекция роли</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.roleSummary ? (
                <>
                  <p>Роль: {data.roleSummary.role}</p>
                  <p>Открытых задач: {data.roleSummary.open_tasks}</p>
                  <p>Просроченных задач: {data.roleSummary.overdue_tasks}</p>
                  <p>
                    Просроченных сроков: {data.roleSummary.overdue_deadlines}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">
                  Сводка по роли временно недоступна
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Исходящая очередь</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.outbox.slice(0, 5).map((item) => (
                <p key={item.id}>
                  {item.event_type} · {item.status} · попыток {item.attempts}
                </p>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Точки вебхуков</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.webhooks.slice(0, 5).map((item) => (
                <p key={item.id}>
                  {item.code || item.id} ·{" "}
                  {item.is_active ? "активна" : "отключена"}
                </p>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Лента аудита</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.auditItems.length ? (
                data.auditItems.slice(0, 5).map((item) => (
                  <p key={item.id}>
                    {item.action} · {item.object_type}
                  </p>
                ))
              ) : (
                <p className="text-muted-foreground">
                  События аудита отсутствуют
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Готовность интеграций</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.integrationReadiness ? (
                <>
                  <p>
                    Настроено:{" "}
                    {data.integrationReadiness.summary.configured_total}
                  </p>
                  <p>
                    Готово к продакшену:{" "}
                    {data.integrationReadiness.summary.production_ready_total}
                  </p>
                  <p>
                    Заглушки / отключено:{" "}
                    {data.integrationReadiness.summary.non_production_total}
                  </p>
                  <p>
                    Сбоев доставки:{" "}
                    {data.integrationReadiness.webhooks.delivery_failed_total}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">
                  Снимок готовности временно недоступен
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Центр внимания</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.attention ? (
                <>
                  <p>
                    Просроченных задач: {data.attention.summary.overdue_tasks}
                  </p>
                  <p>Скоро срок: {data.attention.summary.due_soon_tasks}</p>
                  <p>
                    Просроченных дедлайнов:{" "}
                    {data.attention.summary.overdue_deadlines}
                  </p>
                  <p>
                    Блокеров готовности:{" "}
                    {data.attention.summary.readiness_blockers}
                  </p>
                  {(data.attention.recommendations || [])
                    .slice(0, 2)
                    .map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                </>
              ) : (
                <p className="text-muted-foreground">
                  Снимок внимания временно недоступен
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Входящие задачи</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.taskInbox ? (
                <>
                  <p>Всего открытых: {data.taskInbox.total}</p>
                  <p>Просрочено: {data.taskInbox.overdue}</p>
                  {data.taskInbox.items.slice(0, 3).map((item) => (
                    <p key={item.id}>
                      {item.title} · {item.priority} ·{" "}
                      {item.overdue ? "просрочено" : "открыта"}
                    </p>
                  ))}
                </>
              ) : (
                <p className="text-muted-foreground">
                  Снимок входящих задач временно недоступен
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
};

export default AdminPage;
