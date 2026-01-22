import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const contractors = [
  { name: "ООО «ТехИнжиниринг»", status: "Активен", risk: "Средний", objects: "3 объекта" },
  { name: "ИП «Строймонтаж»", status: "На проверке", risk: "Высокий", objects: "1 объект" },
  { name: "АО «ЭнергоСервис»", status: "Активен", risk: "Низкий", objects: "5 объектов" }
];

const ContractorsPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Контрагенты/подрядчики" }]} />
      <Button>Добавить подрядчика</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Реестр подрядчиков</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Контрагент</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Риск</TableHead>
              <TableHead>Объекты</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {contractors.map((row) => (
              <TableRow key={row.name}>
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.risk}</TableCell>
                <TableCell>{row.objects}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default ContractorsPage;
