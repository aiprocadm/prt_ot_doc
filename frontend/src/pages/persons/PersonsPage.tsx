import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { ListStateGuard } from "@/components/common/ListStateGuard";
import { Can } from "@/components/permissions/Can";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PersonFormDialog } from "@/features/persons/PersonFormDialog";
import { PersonTable } from "@/features/persons/PersonTable";
import { PERMISSIONS } from "@/permissions/permissions";
import { ROUTES } from "@/router/routes";
import { usePersonsStore } from "@/stores/persons";
import type { PersonDto } from "@/types/dto/persons";

const PersonsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { list, pagination, loading, error, items } = usePersonsStore();
  const [selectedPerson, setSelectedPerson] = useState<PersonDto | null>(null);
  const focusedPersonId = searchParams.get("person_id") ?? undefined;

  const PERSON_STATUS_LABELS: Record<string, string> = useMemo(
    () => ({
      active: "Активен",
      inactive: "Неактивен",
      dismissed: "Уволен"
    }),
    []
  );

  useEffect(() => {
    list();
  }, [list]);

  useEffect(() => {
    if (!focusedPersonId) return;
    const focused = items.find((person) => person.id === focusedPersonId);
    if (focused) {
      setSelectedPerson(focused);
    }
  }, [focusedPersonId, items]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: ROUTES.DASHBOARD }, { label: "Сотрудники" }]} />
      <RegistryPageHeader
        title="Сотрудники"
        description="Карточка сотрудника с вкладками по обучению, СИЗ, рискам и медосмотрам."
        stats={[{ label: "Сотрудников", value: pagination.total }]}
        actions={
          <Can permission={PERMISSIONS.PERSON_CREATE}>
            {(allowed) => (
              <PersonFormDialog
                trigger={
                  <Button
                    disabled={!allowed}
                    title={!allowed ? "Недостаточно прав для добавления сотрудника" : undefined}
                  >
                    Добавить
                  </Button>
                }
                onSubmitted={(person) => {
                  setSelectedPerson(person);
                  const next = new URLSearchParams(searchParams);
                  next.set("person_id", person.id);
                  setSearchParams(next, { replace: true });
                  toast.success(`Сотрудник "${person.full_name}" добавлен и открыт в карточке`);
                  list();
                }}
              />
            )}
          </Can>
        }
      />
      <Card>
        <CardContent className="py-6">
          <ListStateGuard
            error={error}
            loading={loading}
            itemsCount={items.length}
            loadingLabel="Загрузка сотрудников"
            emptyTitle="Сотрудники не найдены"
            emptyDescription="Добавьте первого сотрудника или измените фильтры поиска."
            onRetry={() => void list()}
          >
            <PersonTable onSelect={setSelectedPerson} />
          </ListStateGuard>
        </CardContent>
      </Card>
      {selectedPerson && (
        <Card>
          <CardContent className="space-y-4 py-6">
            <h2 className="text-xl font-semibold">{selectedPerson.full_name}</h2>
            {focusedPersonId ? (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="ghost" asChild>
                  <Link to="/persons">Сбросить фокус</Link>
                </Button>
                <Button size="sm" variant="outline" asChild>
                  <Link to={`/documents/quick-generate?person_id=${encodeURIComponent(selectedPerson.id)}&company_id=${encodeURIComponent(selectedPerson.company_id ?? "")}`}>
                    Сформировать документы по случаю
                  </Link>
                </Button>
              </div>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2">
              <Info label="Должность" value={selectedPerson.position} />
              <Info label="Электронная почта" value={selectedPerson.email} />
              <Info label="Телефон" value={selectedPerson.phone} />
              <Info label="Статус" value={PERSON_STATUS_LABELS[selectedPerson.status] ?? selectedPerson.status} />
            </div>
            <Tabs defaultValue="training">
              <TabsList>
                <TabsTrigger value="training">Обучение</TabsTrigger>
                <TabsTrigger value="ppe">СИЗ</TabsTrigger>
                <TabsTrigger value="risks">Риски</TabsTrigger>
                <TabsTrigger value="medical">Медосмотры</TabsTrigger>
              </TabsList>
              <TabsContent value="training">Назначения и удостоверения доступны в модуле обучения.</TabsContent>
              <TabsContent value="ppe">Нормы выдачи и история СИЗ отображаются в модуле СИЗ.</TabsContent>
              <TabsContent value="risks">Связанные оценки рисков и мероприятия доступны в реестре рисков.</TabsContent>
              <TabsContent value="medical">План медосмотров и статусы прохождения доступны в мед-модуле.</TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

const Info = ({ label, value }: { label: string; value?: string | null }) => (
  <div>
    <div className="text-xs uppercase text-muted-foreground">{label}</div>
    <div className="text-sm font-medium">{value ?? "—"}</div>
  </div>
);

export default PersonsPage;
