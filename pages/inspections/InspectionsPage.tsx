import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/common/StatusBadge";

const inspections = [
  { id: "INSP-77", type: "Плановая", site: "Склад 2", status: "processing", due: "30.09.2024" },
  { id: "INSP-78", type: "Внеплановая", site: "Цех 1", status: "draft", due: "10.09.2024" },
  { id: "INSP-79", type: "Проверка подрядчика", site: "Объект 8", status: "ready", due: "05.09.2024" }
];

const InspectionsPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Проверки/предписания" }]} />
      <Button>Создать проверку</Button>
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">План проверок и предписаний</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Тип</TableHead>
              <TableHead>Площадка</TableHead>
              <TableHead>Срок</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {inspections.map((inspection) => (
              <TableRow key={inspection.id}>
                <TableCell className="font-medium">{inspection.id}</TableCell>
                <TableCell>{inspection.type}</TableCell>
                <TableCell>{inspection.site}</TableCell>
                <TableCell>{inspection.due}</TableCell>
                <TableCell>
                  <StatusBadge status={inspection.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default InspectionsPage;
