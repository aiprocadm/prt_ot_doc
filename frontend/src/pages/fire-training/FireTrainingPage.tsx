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

const FireTrainingPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getFireTrainingSnapshot(), []),
    initialData: {
      templates: [],
      journals: [],
      overdueEntries: [],
      programs: [],
    },
    errorMessage: "Не удалось загрузить журналы и учения",
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пожарная безопасность · инструктажи и учения"
        description="Раздел связан с реальными журналами, шаблонами инструктажей и просроченными записями инструктажей."
        actions={
          <Button asChild variant="outline">
            <Link to="/briefings">Открыть инструктажи</Link>
          </Button>
        }
        stats={[
          { label: "Шаблоны", value: data.templates.length },
          { label: "Журналы", value: data.journals.length },
          { label: "Просрочено", value: data.overdueEntries.length },
          { label: "Программы", value: data.programs.length },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка журналов" /> : null}
      {!loading && !error && data.overdueEntries.length > 0 ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">
              Блокеры и дальнейшие действия
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>
              Найдено просроченных записей инструктажей:{" "}
              {data.overdueEntries.length}. Требуется закрыть задолженность до
              следующей волны проверок.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to="/briefings">Открыть журналы инструктажей</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/tasks?type=briefing">Открыть связанные задачи</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {!loading &&
      !error &&
      data.templates.length + data.journals.length === 0 ? (
        <EmptyState
          title="Нет данных по инструктажам"
          description="Создайте шаблоны или журналы инструктажей."
        />
      ) : null}
      {!loading && !error ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Шаблоны</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.templates.slice(0, 5).map((item) => (
                <p key={item.id}>
                  {item.title} · {item.status}
                </p>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Журналы</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.journals.slice(0, 5).map((item) => (
                <p key={item.id}>
                  {item.title} · {item.status}
                </p>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Просроченные записи</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {data.overdueEntries.slice(0, 5).map((item) => (
                <p key={item.id}>
                  {item.briefing_type} · {item.status}
                </p>
              ))}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
};

export default FireTrainingPage;
