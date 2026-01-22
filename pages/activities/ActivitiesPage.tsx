import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/common/StatusBadge";

const activities = [
  { id: "CAPA-34", title: "Установить ограждение на эстакаде", source: "Инцидент", owner: "Смирнов А.А.", status: "processing" },
  { id: "CAPA-35", title: "Обновить инструктаж для работников склада", source: "Риск", owner: "Козлова Л.Н.", status: "ready" },
  { id: "CAPA-36", title: "Проверить СИЗ на участке 3", source: "Предписание", owner: "Плотников Д.С.", status: "draft" }
];

const ActivitiesPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Мероприятия" }]} />
      <Button>Создать мероприятие</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">CAPA-реестр</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Мероприятие</TableHead>
              <TableHead>Источник</TableHead>
              <TableHead>Ответственный</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {activities.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.id}</TableCell>
                <TableCell>{item.title}</TableCell>
                <TableCell>{item.source}</TableCell>
                <TableCell>{item.owner}</TableCell>
                <TableCell>
                  <StatusBadge status={item.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default ActivitiesPage;
