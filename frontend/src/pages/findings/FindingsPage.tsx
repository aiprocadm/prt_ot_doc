import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const findings = [
  { id: "F-102", source: "inspection", site: "Цех 1", severity: "high", status: "open" },
  { id: "F-103", source: "incident", site: "Склад 4", severity: "critical", status: "in_progress" },
  { id: "F-104", source: "manual", site: "Подрядчик А", severity: "medium", status: "resolved" }
];

const FindingsPage = () => (
  <div className="space-y-6">
    <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Findings" }]} />
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Единый реестр findings</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Источник</TableHead>
              <TableHead>Площадка</TableHead>
              <TableHead>Критичность</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {findings.map((finding) => (
              <TableRow key={finding.id}>
                <TableCell className="font-medium">{finding.id}</TableCell>
                <TableCell>{finding.source}</TableCell>
                <TableCell>{finding.site}</TableCell>
                <TableCell>
                  <Badge variant={finding.severity === "critical" ? "destructive" : "secondary"}>{finding.severity}</Badge>
                </TableCell>
                <TableCell>{finding.status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

export default FindingsPage;
