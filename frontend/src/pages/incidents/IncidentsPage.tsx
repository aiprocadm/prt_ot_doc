import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/common/StatusBadge";

const incidents = [
  { id: "INC-18", title: "Падение с высоты", site: "Объект 12", status: "processing", date: "12.08.2024" },
  { id: "INC-19", title: "Отказ оборудования", site: "Цех 4", status: "draft", date: "15.08.2024" },
  { id: "INC-20", title: "Возгорание кабеля", site: "Подстанция", status: "ready", date: "21.08.2024" }
];

const IncidentsPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Инциденты/НС" }]} />
      <Button>Зарегистрировать инцидент</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Инциденты и расследования</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Событие</TableHead>
              <TableHead>Площадка</TableHead>
              <TableHead>Дата</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {incidents.map((incident) => (
              <TableRow key={incident.id}>
                <TableCell className="font-medium">{incident.id}</TableCell>
                <TableCell>{incident.title}</TableCell>
                <TableCell>{incident.site}</TableCell>
                <TableCell>{incident.date}</TableCell>
                <TableCell>
                  <StatusBadge status={incident.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default IncidentsPage;
