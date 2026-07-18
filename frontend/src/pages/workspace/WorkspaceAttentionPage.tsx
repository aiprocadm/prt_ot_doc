import { Bell, CalendarDays, ClipboardList, HardHat, HeartPulse, Search, ShieldAlert, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { AttentionPanel } from "@/components/common/AttentionPanel";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

const quickLinks = [
  { to: "/tasks", label: "Задачи и сроки", icon: ClipboardList, description: "Единый inbox обязательств и напоминаний." },
  { to: "/notifications", label: "Уведомления", icon: Bell, description: "События и эскалации по ролям." },
  { to: "/calendar", label: "Календарь", icon: CalendarDays, description: "Дедлайны и контрольные точки." },
  { to: "/search", label: "Поиск", icon: Search, description: "Быстрый доступ к сущностям и файлам." }
];

const attentionWidgets: Array<{
  title: string;
  description: string;
  to: string;
  cta: string;
  icon: typeof ShieldAlert;
  permissions: Permission[];
}> = [
  {
    title: "Просроченное обучение",
    description: "Сотрудники с истекшими сроками обучения и назначениями к обновлению.",
    to: "/tasks?type=training_plan&overdue=true",
    cta: "Открыть задачи по обучению",
    icon: ShieldAlert,
    permissions: [PERMISSIONS.TRAINING_VIEW]
  },
  {
    title: "Истечения медосмотров",
    description: "Персонал с просроченными или истекающими медицинскими допусками.",
    to: "/medical?status=expired",
    cta: "Открыть медосмотры",
    icon: HeartPulse,
    permissions: [PERMISSIONS.MEDICAL_VIEW]
  },
  {
    title: "Действия по СИЗ",
    description: "Просроченные выдачи, возвраты и пополнение остатков СИЗ.",
    to: "/ppe",
    cta: "Открыть СИЗ",
    icon: HardHat,
    permissions: [PERMISSIONS.PPE_VIEW]
  },
  {
    title: "Действия по документам",
    description: "Документы, требующие ревью, подписи или обновления версии.",
    to: "/documents?needs_action=true",
    cta: "Открыть документы",
    icon: ShieldCheck,
    permissions: [PERMISSIONS.DOCUMENT_VIEW]
  },
  {
    title: "Проверки, предписания и корректирующие",
    description: "Ближайшие инспекции, открытые предписания и незакрытые корректирующие действия.",
    to: "/inspections?due=soon",
    cta: "Открыть инспекции",
    icon: ClipboardList,
    permissions: [PERMISSIONS.INSPECTION_VIEW]
  }
];

export default function WorkspaceAttentionPage() {
  const { can } = useAbility();
  const availableWidgets = attentionWidgets.filter((widget) => widget.permissions.every((permission) => can(permission)));

  return (
    <div className="space-y-6 p-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Центр внимания" }]} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Центр внимания</h1>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
          Сводка рисков, блокеров готовности и задач — те же данные, что на дашборде. Ниже — быстрые переходы в
          смежные разделы (доступ по ролям).
        </p>
      </div>
      <AttentionPanel showOuterTitle={false} />
      {availableWidgets.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Фокус OT/ПБ</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {availableWidgets.map(({ title, description, to, cta, icon: Icon }) => (
              <Card key={title} className="h-full border-l-4 border-l-blue-500">
                <CardHeader className="space-y-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Icon className="h-4 w-4 text-blue-500" />
                    {title}
                  </CardTitle>
                  <CardDescription>{description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Link to={to} className="inline-flex text-sm font-medium text-blue-600 hover:underline">
                    {cta} — 1–2 клика до действия →
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Быстрые переходы</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {quickLinks.map(({ to, label, icon: Icon, description }) => (
            <Link key={to} to={to} className="block">
              <Card className="h-full transition-colors hover:bg-muted/40">
                <CardHeader className="flex flex-row items-center gap-3 space-y-0">
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <CardTitle className="text-base">{label}</CardTitle>
                    <CardDescription>{description}</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-primary">Перейти →</CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
