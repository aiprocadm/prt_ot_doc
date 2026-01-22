import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const FireTrainingPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "ПБ · Инструктажи/учения" }]} />
      <div className="flex gap-2">
        <Button>Запланировать учение</Button>
        <Button variant="outline">Создать журнал</Button>
      </div>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Журналы и учения</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        В этом разделе ведутся электронные журналы противопожарных инструктажей и график учений.
      </CardContent>
    </Card>
  </div>
);

export default FireTrainingPage;
