import { Link } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

const adminBlocks = [
  {
    title: "Биллинг и тариф",
    description: "Тариф, лимиты, usage и статус оплаты.",
    to: "/admin/billing"
  },
  {
    title: "Outbox / очередь событий",
    description: "Очередь исходящих событий, статусы доставки, повторные попытки.",
    to: "/admin/outbox"
  },
  {
    title: "Шаблоны документов",
    description: "Версионирование, публикация, запрет удаления используемых шаблонов.",
    to: "/templates"
  },
  {
    title: "Макеты (Layout Presets)",
    description: "Настройка колонтитулов, токены замены, PDF-preview.",
    to: "/admin/layout-presets"
  },
  {
    title: "Маршруты согласования",
    description: "CRUD маршрутов, делегирование, SLA и эскалации.",
    to: "/approval-routes"
  },
  {
    title: "Интеграции",
    description: "Webhook-эндпоинты, SSO, ЭДО, КЭП/УКЭП, МЧД.",
    to: "/integrations"
  },
  {
    title: "НПА / Нормативная база",
    description: "Реестр нормативно-правовых актов и требований.",
    to: "/npa"
  },
  {
    title: "Журнал аудита",
    description: "Полный лог изменений, авторизаций и действий пользователей.",
    to: "/audit"
  },
  {
    title: "Настройки платформы",
    description: "Глобальные параметры арендатора, SMTP, уведомления.",
    to: "/settings"
  },
  {
    title: "Справочники",
    description: "Опасности, нормы СИЗ, чек-листы проверок.",
    to: "/reference"
  }
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
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/audit">Журнал аудита</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/settings">Настройки</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {adminBlocks.map((block) => (
          <Card key={block.title} className="transition hover:shadow-md">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">{block.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{block.description}</p>
              {block.to && (
                <Button size="sm" variant="outline" asChild>
                  <Link to={block.to}>Открыть</Link>
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default AdminPage;
