import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const ppeRows = [
  { employee: "Климова Е.А.", role: "Сварщик", due: "15.10.2024", issued: "12/14", size: "M" },
  { employee: "Шустов И.И.", role: "Электромонтер", due: "05.11.2024", issued: "8/10", size: "L" },
  { employee: "Громова Л.П.", role: "Мастер", due: "21.09.2024", issued: "6/6", size: "S" }
];

const PpePage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "СИЗ и склады" }]} />
      <div className="flex gap-2">
        <Button>Быстрая выдача</Button>
        <Button variant="outline">Остатки склада</Button>
      </div>
    </div>
    <div className="grid gap-4 md:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Нормы по должностям</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">12 комплектов, 4 обновлены в этом месяце.</CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Просрочка носки</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">7 сотрудников требуют замену в 30 дней.</CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Сертификаты партий</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">3 партии без прикрепленных паспортов.</CardContent>
      </Card>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Карточки выдачи СИЗ</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Сотрудник</TableHead>
              <TableHead>Должность</TableHead>
              <TableHead>Выдано</TableHead>
              <TableHead>Срок замены</TableHead>
              <TableHead>Размер</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ppeRows.map((row) => (
              <TableRow key={row.employee}>
                <TableCell className="font-medium">{row.employee}</TableCell>
                <TableCell>{row.role}</TableCell>
                <TableCell>{row.issued}</TableCell>
                <TableCell>{row.due}</TableCell>
                <TableCell>{row.size}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default PpePage;
