import { useCallback } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { deniedNotice } from "@/api/partial";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";

const ReferencePage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getReferenceSnapshot(), []),
    initialData: {
      denied: [],
      npa: [],
      ppeItems: [],
      programs: [],
      templates: [],
      briefingTemplates: [],
    },
    errorMessage: "Не удалось загрузить справочники",
  });

  const cards = [
    {
      title: "НПА",
      count: data.npa.length,
      hint: "Нормативные акты",
      to: "/npa",
    },
    {
      title: "СИЗ",
      count: data.ppeItems.length,
      hint: "Номенклатура и нормы",
      to: "/ppe",
    },
    {
      title: "Программы обучения",
      count: data.programs.length,
      hint: "Учебные программы и группы",
      to: "/training",
    },
    {
      title: "Шаблоны документов",
      count: data.templates.length,
      hint: "Версии и публикация",
      to: "/templates",
    },
    {
      title: "Шаблоны инструктажей",
      count: data.briefingTemplates.length,
      hint: "Журналы и mobile flows",
      to: "/briefings",
    },
    {
      // BIZ-54-57 срез-3: вход в карточку площадки 360°. Числа НЕТ намеренно:
      // площадки читает только администратор, и «0» на месте отказа в доступе
      // прочитали бы как «площадок нет».
      title: "Площадки",
      hint: "Статус объекта по всем дисциплинам",
      to: "/sites",
    },
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Справочники"
        description="Вместо статических карточек страница теперь показывает фактическое наполнение тенанта по НПА, СИЗ, обучению, шаблонам и инструктажам."
        actions={
          <Button asChild variant="outline">
            <Link to="/templates">Шаблоны документов</Link>
          </Button>
        }
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {deniedNotice(data.denied) ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50">
          {deniedNotice(data.denied)}
        </p>
      ) : null}
      {loading ? <LoadingScreen label="Загрузка справочников" /> : null}
      {!loading &&
      !error &&
      cards.every((item) => item.count === undefined || item.count === 0) ? (
        <EmptyState
          title="Справочники пока пусты"
          description="Импортируйте справочники или загрузите первые записи."
        />
      ) : null}
      {!loading && !error ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((item) => (
            <Card key={item.title}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-base">
                  <span>{item.title}</span>
                  {item.count === undefined ? null : <span>{item.count}</span>}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>{item.hint}</p>
                <Button asChild size="sm" variant="outline">
                  <Link to={item.to}>Открыть</Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default ReferencePage;
