import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

const adminBlocks = [
  { title: "Биллинг", description: "Тариф, лимиты, usage и статус оплаты.", to: "/admin/billing" },
  { title: "Роли и права", description: "RBAC/ABAC матрица, атрибуты, маскирование ПДн." },
  { title: "Маршруты согласования", description: "CRUD маршрутов, делегирование, SLA и эскалации." },
  { title: "Шаблоны документов", description: "Версионирование, запрет удаления используемых шаблонов." },
  { title: "Методики рисков", description: "Матрицы, версии, шкалы вероятности и тяжести." },
  { title: "Интеграции", description: "SSO, ЭДО, КЭП/УКЭП, МЧД, внешние справочники." }
];

const AdminPage = () => {
  const { can } = useAbility();

  if (!can(PERMISSIONS.ADMIN_MANAGE_ROLES)) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Администрирование" }]} />
        <Button>Создать правило доступа</Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {adminBlocks.map((block) => (
          <Card key={block.title}>
            <CardHeader>
              <CardTitle className="text-sm font-semibold">{block.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{block.description}{(block as {to?: string}).to ? <div className="mt-2"><a className="underline" href={(block as {to: string}).to}>Открыть</a></div> : null}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default AdminPage;
