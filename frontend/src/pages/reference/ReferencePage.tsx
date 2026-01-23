import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ReferencePage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Справочники" }]} />
      <Button>Импорт справочников</Button>
    </div>
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {[
        "Опасности и меры управления",
        "Нормы СИЗ и классификаторы",
        "Чек-листы проверок",
        "Программы обучения",
        "Методики оценки рисков",
        "Шаблоны документов"
      ].map((item) => (
        <Card key={item}>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">{item}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">Управление версиями, импорт/экспорт.</CardContent>
        </Card>
      ))}
    </div>
  </div>
);

export default ReferencePage;
