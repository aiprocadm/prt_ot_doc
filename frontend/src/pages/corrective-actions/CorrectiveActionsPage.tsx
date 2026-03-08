import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const actions = [
  { id: "CA-44", title: "Замена СИЗ", responsible: "Иванов И.И.", due: "2026-04-14", status: "overdue", effectiveness: "unknown" },
  { id: "CA-45", title: "Внеплановый инструктаж", responsible: "Петров П.П.", due: "2026-04-18", status: "in_progress", effectiveness: "unknown" },
  { id: "CA-46", title: "Изменение регламента", responsible: "Сидоров С.С.", due: "2026-04-10", status: "verified", effectiveness: "effective" }
];

const CorrectiveActionsPage = () => (
  <div className="space-y-6">
    <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Корректирующие действия" }]} />
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Реестр CAPA</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Мероприятие</TableHead>
              <TableHead>Ответственный</TableHead>
              <TableHead>Срок</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Эффективность</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {actions.map((action) => (
              <TableRow key={action.id}>
                <TableCell className="font-medium">{action.id}</TableCell>
                <TableCell>{action.title}</TableCell>
                <TableCell>{action.responsible}</TableCell>
                <TableCell>{action.due}</TableCell>
                <TableCell>{action.status}</TableCell>
                <TableCell>{action.effectiveness}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default CorrectiveActionsPage;
