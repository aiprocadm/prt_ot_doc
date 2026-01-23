import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const medicalChecks = [
  { employee: "Рябова Н.В.", position: "Оператор", status: "Просрочено", due: "02.09.2024" },
  { employee: "Титов А.С.", position: "Слесарь", status: "Назначено", due: "12.10.2024" },
  { employee: "Кудряшова И.А.", position: "Инженер", status: "Пройдено", due: "20.12.2024" }
];

const MedicalPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Медосмотры/допуски" }]} />
      <Button>Назначить медосмотр</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">График медосмотров</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Сотрудник</TableHead>
              <TableHead>Должность</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Следующий срок</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {medicalChecks.map((row) => (
              <TableRow key={row.employee}>
                <TableCell className="font-medium">{row.employee}</TableCell>
                <TableCell>{row.position}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.due}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default MedicalPage;
