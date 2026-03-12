import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const connectors = [
  { name: "ЭДО Контур", direction: "outbound", status: "ready", lastSync: "сегодня 10:42" },
  { name: "1С ЗУП", direction: "bidirectional", status: "processing", lastSync: "сегодня 10:31" },
  { name: "SIEM", direction: "outbound", status: "warning", lastSync: "вчера 23:15" }
] as const;

const IntegrationsPage = () => {
  return (
    <div className="space-y-4">
      <RegistryPageHeader title="Интеграции" description="Контроль API-интеграций, синхронизации и статусов обмена." />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Подключения</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Интеграция</TableHead>
                <TableHead>Направление</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Последняя синхронизация</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {connectors.map((connector) => (
                <TableRow key={connector.name}>
                  <TableCell className="font-medium">{connector.name}</TableCell>
                  <TableCell>{connector.direction}</TableCell>
                  <TableCell>
                    <StatusBadge status={connector.status} />
                  </TableCell>
                  <TableCell>{connector.lastSync}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default IntegrationsPage;
