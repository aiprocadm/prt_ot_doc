import { FileText, Package, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const links = [
  {
    to: "/documents",
    label: "Документы",
    icon: FileText,
    description: "Проверка готовности и статусов выпуска."
  },
  {
    to: "/generation",
    label: "Генерация",
    icon: Package,
    description: "Мастер и контроль входных данных перед выпуском."
  },
  {
    to: "/search",
    label: "Поиск",
    icon: Search,
    description: "Поиск по архиву и метаданным для выявления пробелов."
  }
];

export default function WorkspaceDataQualityPage() {
  return (
    <div className="space-y-6 p-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Качество данных" }]} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Качество данных</h1>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
          Точки входа для контроля полноты документного контура и связанных артефактов (соответствует волне UX ТЗ:
          explainability readiness и навигация без тупиков).
        </p>
      </div>
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
  );
}
