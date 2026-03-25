import { useEffect, useState } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PersonFormDialog } from "@/features/persons/PersonFormDialog";
import { PersonTable } from "@/features/persons/PersonTable";
import { PERMISSIONS } from "@/permissions/permissions";
import { usePersonsStore } from "@/stores/persons";
import type { PersonDto } from "@/types/dto/persons";

const PersonsPage = () => {
  const { list, pagination, loading, error, items } = usePersonsStore();
  const [selectedPerson, setSelectedPerson] = useState<PersonDto | null>(null);

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Сотрудники" }]} />
      <RegistryPageHeader
        title="Сотрудники"
        description="Карточка сотрудника с вкладками по обучению, СИЗ, рискам и медосмотрам."
        stats={[{ label: "Сотрудников", value: pagination.total }]}
        actions={
          <PersonFormDialog
            trigger={
              <Can
                permission={PERMISSIONS.PERSON_CREATE}
                fallback={<Button disabled title="Недостаточно прав для добавления сотрудника">Добавить</Button>}
              >
                <Button>Добавить</Button>
              </Can>
            }
            onSubmitted={(person) => {
              setSelectedPerson(person);
              list();
            }}
          />
        }
      />
      <Card>
        <CardContent className="py-6">
          <ErrorState error={error ?? undefined} onRetry={() => void list()} />
          {loading ? <LoadingScreen label="Загрузка сотрудников" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Сотрудники не найдены" description="Добавьте первого сотрудника или измените фильтры поиска." />
          ) : null}
          {!loading && !error && items.length > 0 ? <PersonTable onSelect={setSelectedPerson} /> : null}
        </CardContent>
      </Card>
      {selectedPerson && (
        <Card>
          <CardContent className="space-y-4 py-6">
            <h2 className="text-xl font-semibold">{selectedPerson.full_name}</h2>
            <div className="grid gap-2 md:grid-cols-2">
              <Info label="Должность" value={selectedPerson.position} />
              <Info label="Email" value={selectedPerson.email} />
              <Info label="Телефон" value={selectedPerson.phone} />
              <Info label="Статус" value={selectedPerson.status} />
            </div>
            <Tabs defaultValue="training">
              <TabsList>
                <TabsTrigger value="training">Training</TabsTrigger>
                <TabsTrigger value="ppe">PPE</TabsTrigger>
                <TabsTrigger value="risks">Risks</TabsTrigger>
                <TabsTrigger value="medical">Medical</TabsTrigger>
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
