import { useCallback } from "react";
import { Link } from "react-router-dom";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
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
      {loading ? <LoadingScreen label="Загрузка справочников" /> : null}
      {!loading && !error && cards.every((item) => item.count === 0) ? (
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
                  <span>{item.count}</span>
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
