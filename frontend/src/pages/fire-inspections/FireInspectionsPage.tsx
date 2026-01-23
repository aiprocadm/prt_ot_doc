import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const fireInspections = [
  { id: "FS-11", site: "Цех 2", checklist: "ПБ-ЧЛ-01", status: "В работе" },
  { id: "FS-12", site: "Склад ГСМ", checklist: "ПБ-ЧЛ-03", status: "Назначено" },
  { id: "FS-13", site: "Офис", checklist: "ПБ-ЧЛ-07", status: "Завершено" }
];

const FireInspectionsPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "ПБ · Проверки/предписания" }]} />
      <Button>Новая проверка</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Проверки ПБ</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Площадка</TableHead>
              <TableHead>Чек-лист</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fireInspections.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-medium">{row.id}</TableCell>
                <TableCell>{row.site}</TableCell>
                <TableCell>{row.checklist}</TableCell>
                <TableCell>{row.status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default FireInspectionsPage;
