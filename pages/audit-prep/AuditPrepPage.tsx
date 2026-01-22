import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const packages = [
  { name: "Ростехнадзор · Плановая", readiness: "86%", gaps: "3 документа", next: "15.10.2024" },
  { name: "МЧС · Внеплановая", readiness: "72%", gaps: "2 подписи", next: "20.09.2024" },
  { name: "Внутренний аудит", readiness: "94%", gaps: "1 чек-лист", next: "05.10.2024" }
];

const AuditPrepPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Подготовка к проверке" }]} />
      <Button>Сформировать пакет</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Пакеты документов</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Пакет</TableHead>
              <TableHead>Готовность</TableHead>
              <TableHead>Пробелы</TableHead>
              <TableHead>Дата проверки</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {packages.map((pkg) => (
              <TableRow key={pkg.name}>
                <TableCell className="font-medium">{pkg.name}</TableCell>
                <TableCell>{pkg.readiness}</TableCell>
                <TableCell>{pkg.gaps}</TableCell>
                <TableCell>{pkg.next}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default AuditPrepPage;
