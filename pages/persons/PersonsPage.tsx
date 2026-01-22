import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PersonFormDialog } from "@/features/persons/PersonFormDialog";
import { PersonTable } from "@/features/persons/PersonTable";
import { usePersonsStore } from "@/stores/persons";
import type { PersonDto } from "@/types/dto/persons";

const PersonsPage = () => {
  const { list } = usePersonsStore();
  const [selectedPerson, setSelectedPerson] = useState<PersonDto | null>(null);

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Сотрудники" }]} />
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Сотрудники</h1>
          <PersonFormDialog
            trigger={<Button>Добавить</Button>}
            onSubmitted={(person) => {
              setSelectedPerson(person);
              list();
            }}
          />
        </div>
      </div>
      <Card>
        <CardContent className="py-6">
          <PersonTable onSelect={setSelectedPerson} />
        </CardContent>
      </Card>
      {selectedPerson && (
        <Card>
          <CardContent className="space-y-2 py-6">
            <h2 className="text-xl font-semibold">{selectedPerson.full_name}</h2>
            <div className="grid gap-2 md:grid-cols-2">
              <Info label="Должность" value={selectedPerson.position} />
              <Info label="Email" value={selectedPerson.email} />
              <Info label="Телефон" value={selectedPerson.phone} />
              <Info label="Статус" value={selectedPerson.status} />
            </div>
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
