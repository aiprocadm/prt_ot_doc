import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const objects = [
  { name: "Склад ГСМ", category: "B1", status: "Паспорт актуален", responsible: "Соколова Е.П." },
  { name: "Цех покраски", category: "B2", status: "Требует пересмотра", responsible: "Титов А.С." },
  { name: "Административный блок", category: "D", status: "В норме", responsible: "Левина Н.Н." }
];

const FireSafetyPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "ПБ · Объекты защиты" }]} />
      <Button>Добавить объект</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Объекты защиты и категории</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Объект</TableHead>
              <TableHead>Категория</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Ответственный</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {objects.map((row) => (
              <TableRow key={row.name}>
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell>{row.category}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.responsible}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default FireSafetyPage;
