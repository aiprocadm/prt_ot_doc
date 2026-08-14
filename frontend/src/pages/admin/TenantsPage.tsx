import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { isNotManagingTenantError, tenantsApi } from "@/api/tenants";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FleetUsagePanel } from "@/features/tenants/FleetUsagePanel";
import { TenantFormDialog } from "@/features/tenants/TenantFormDialog";
import { TenantPlanDialog } from "@/features/tenants/TenantPlanDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  PlanCatalog,
  TenantFleetItem,
  TenantFleetPage,
} from "@/types/dto/tenants";

const KIND_LABELS: Record<string, string> = {
  customer: "Заказчик",
  branch: "Филиал",
  contractor: "Подрядчик",
  reseller: "Реселлер (партнёр)",
};

const emptyFleet: TenantFleetPage = {
  items: [],
  total: 0,
  managing_tenant_slug: "",
  // Пока ответ не пришёл, считаем смотрящего партнёром с наименьшими правами:
  // мигнуть кнопкой смены тарифа и отобрать её — хуже, чем показать её на
  // полсекунды позже.
  viewer_level: "reseller",
  can_manage_commercials: false,
};
const emptyPlans: PlanCatalog = { plans: [], features: [] };

const TenantsPage = () => {
  const loader = useCallback(() => tenantsApi.list(), []);
  const res = useAsyncResource<TenantFleetPage>({
    loader,
    initialData: emptyFleet,
    errorMessage: "Не удалось загрузить список тенантов",
  });

  const plansLoader = useCallback(() => tenantsApi.plans(), []);
  const plansRes = useAsyncResource<PlanCatalog>({
    loader: plansLoader,
    initialData: emptyPlans,
    // A 403 here is the same "not the managing tenant" case the list handles below;
    // swallow it so it never surfaces as a page error.
    errorMessage: "",
  });
  const plans = plansRes.data.plans;
  const planTitle = (code?: string | null) =>
    plans.find((plan) => plan.code === code)?.title ?? "Свой набор";

  const reload = () => {
    void res.reload().catch(() => undefined);
    void plansRes.reload().catch(() => undefined);
  };

  const registry = useLocalRegistry<TenantFleetItem>({
    items: res.data.items,
    match: (item, query) =>
      [item.tenant.name, item.tenant.slug, item.tenant.contact_email]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const managingSlug = res.data.managing_tenant_slug;
  // Оба признака — из ответа сервера (BIZ-52 срез-2). Партнёр видит тот же
  // экран, но про СВОИХ клиентов и без коммерческих кнопок.
  const canManageCommercials = res.data.can_manage_commercials;
  const isPlatformOwner = res.data.viewer_level === "platform";

  const toggleStatus = async (item: TenantFleetItem, nextActive: boolean) => {
    try {
      await tenantsApi.setStatus(item.tenant.id, nextActive);
      toast.success(
        nextActive
          ? `Доступ для «${item.tenant.name}» включён`
          : `Доступ для «${item.tenant.name}» приостановлен`,
      );
      reload();
    } catch {
      /* toast is raised by the global error interceptor */
    }
  };

  const columns: ColumnDef<TenantFleetItem, unknown>[] = [
    {
      accessorKey: "tenant.name",
      header: "Название",
      cell: ({ row }) => (
        <div className="space-y-1">
          <span className="font-medium">{row.original.tenant.name}</span>
          {row.original.tenant.slug === managingSlug ? (
            <Badge variant="outline" className="ml-2">
              управляющий
            </Badge>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {row.original.tenant.contact_email}
          </p>
        </div>
      ),
    },
    {
      accessorKey: "tenant.slug",
      header: "Слаг",
      cell: ({ row }) => (
        <code className="text-xs">{row.original.tenant.slug}</code>
      ),
    },
    {
      id: "kind",
      header: "Тип",
      cell: ({ row }) =>
        KIND_LABELS[row.original.tenant.kind ?? "customer"] ?? "—",
    },
    {
      id: "quotas",
      header: "Лимиты",
      cell: ({ row }) => {
        const quotas = row.original.quotas;
        if (!quotas) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-xs">
            {quotas.max_doc_generations_per_month} док/мес ·{" "}
            {quotas.max_storage_mb} МБ
          </span>
        );
      },
    },
    {
      id: "plan",
      header: "Тариф",
      cell: ({ row }) => {
        const item = row.original;
        return (
          <div className="flex items-center gap-2">
            <Badge variant={item.plan ? "default" : "secondary"}>
              {planTitle(item.plan)}
            </Badge>
            {/* Смена тарифа — только у владельца платформы (BIZ-52 срез-2):
                у партнёра пока нет собственного потолка, и сервер такой запрос
                отвергает. Показывать кнопку, которая всегда отказывает, хуже,
                чем не показывать её вовсе. Признак берём из ответа сервера, а
                не выводим из роли: вторая правда о правах однажды разойдётся. */}
            {canManageCommercials ? (
              <Can permission={PERMISSIONS.ADMIN_MANAGE_TENANTS}>
                <TenantPlanDialog
                  item={item}
                  plans={plans}
                  onSubmitted={reload}
                  trigger={
                    <Button variant="ghost" size="sm">
                      Изменить
                    </Button>
                  }
                />
              </Can>
            ) : null}
          </div>
        );
      },
    },
    {
      id: "status",
      header: "Доступ",
      cell: ({ row }) => {
        const item = row.original;
        const isManaging = item.tenant.slug === managingSlug;
        return (
          <Can
            permission={PERMISSIONS.ADMIN_MANAGE_TENANTS}
            fallback={
              <Badge variant={item.tenant.is_active ? "default" : "secondary"}>
                {item.tenant.is_active ? "активен" : "приостановлен"}
              </Badge>
            }
          >
            <div className="flex items-center gap-2">
              <Switch
                checked={item.tenant.is_active}
                disabled={isManaging}
                aria-label={`Доступ для ${item.tenant.name}`}
                onCheckedChange={(next) => void toggleStatus(item, next)}
              />
              <span className="text-xs text-muted-foreground">
                {item.tenant.is_active ? "активен" : "приостановлен"}
              </span>
            </div>
          </Can>
        );
      },
    },
  ];

  // A 403 here is not a failure to report as an error: it simply means this tenant is not
  // the managing one, which is the normal state for every customer tenant.
  if (!res.loading && isNotManagingTenantError(res.error)) {
    return (
      <div className="space-y-4">
        <RegistryPageHeader
          title="Тенанты"
          description="Управление площадками и подписками."
        />
        <EmptyState
          title="Раздел доступен только управляющему тенанту"
          description="Заводить и приостанавливать другие площадки может администратор управляющего тенанта. Войдите под ним, чтобы продолжить."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title={isPlatformOwner ? "Тенанты" : "Мои клиенты"}
        description={
          isPlatformOwner
            ? "Площадки платформы: создание, доступ по подписке и лимиты."
            : "Клиенты вашей компании: создание и доступ. Тарифы и лимиты задаёт владелец платформы."
        }
        actions={
          <Can
            permission={PERMISSIONS.ADMIN_MANAGE_TENANTS}
            fallback={<Button disabled>Новый тенант</Button>}
          >
            <TenantFormDialog
              trigger={<Button>Новый тенант</Button>}
              onSubmitted={reload}
            />
          </Can>
        }
        stats={[
          {
            label: isPlatformOwner ? "Всего тенантов" : "Всего клиентов",
            value: res.data.total,
          },
          {
            label: "Активных",
            value: res.data.items.filter((item) => item.tenant.is_active)
              .length,
          },
          // Слаг управляющего партнёру не показываем: в его кабинете это чужая
          // служебная подробность, а разд. 52.2 требует убирать упоминания
          // вендора из интерфейса партнёра.
          ...(isPlatformOwner
            ? [{ label: "Управляющий", value: managingSlug || "—" }]
            : []),
        ]}
      />
      {/* BIZ-52 срез-13: расход клиентов. Ручка есть с среза-8, но кабинет её
          не вызывал — партнёр не видел, за что выставлять счёт. */}
      <FleetUsagePanel />
      <ErrorState error={res.error ?? undefined} onRetry={reload} />
      {res.loading ? <LoadingScreen label="Загрузка тенантов" /> : null}
      {!res.loading && !res.error && registry.total === 0 ? (
        <EmptyState
          title="Тенантов пока нет"
          description="Создайте первую площадку кнопкой «Новый тенант»."
        />
      ) : null}
      {!res.loading && !res.error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по названию, слагу и e-mail"
          caption="Реестр тенантов"
        />
      ) : null}
    </div>
  );
};

export default TenantsPage;
