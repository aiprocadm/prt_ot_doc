import { Bell, CalendarDays, ClipboardList, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { AttentionPanel } from "@/components/common/AttentionPanel";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const links = [
  { to: "/tasks", label: "Задачи и сроки", icon: ClipboardList, description: "Единый inbox обязательств и напоминаний." },
  { to: "/notifications", label: "Уведомления", icon: Bell, description: "События и эскалации по ролям." },
  { to: "/calendar", label: "Календарь", icon: CalendarDays, description: "Дедлайны и контрольные точки." },
  { to: "/search", label: "Поиск", icon: Search, description: "Быстрый доступ к сущностям и файлам." }
];

export default function WorkspaceAttentionPage() {
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
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Быстрые переходы</h2>
        <div className="grid gap-4 md:grid-cols-2">
        {links.map(({ to, label, icon: Icon, description }) => (
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
