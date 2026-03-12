import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const deals = [
  { id: "DL-101", client: "АО ТехПром", package: "Пакет Ростехнадзор", amount: "₽ 1 480 000", payment: "processing" },
  { id: "DL-117", client: "ООО СеверЭко", package: "Пакет Экология", amount: "₽ 640 000", payment: "ready" },
  { id: "DL-125", client: "ЗАО МеталлСтрой", package: "Пакет ОТ/ПБ", amount: "₽ 920 000", payment: "draft" }
] as const;

const CrmFinancePage = () => {
  return (
    <div className="space-y-4">
      <RegistryPageHeader title="CRM / Финансы" description="Лиды, сделки, договоры и статусы оплат, связанные с пакетами документов." />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Активные сделки</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Клиент</TableHead>
                <TableHead>Пакет</TableHead>
                <TableHead>Сумма</TableHead>
                <TableHead>Статус оплаты</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {deals.map((deal) => (
                <TableRow key={deal.id}>
                  <TableCell className="font-medium">{deal.id}</TableCell>
                  <TableCell>{deal.client}</TableCell>
                  <TableCell>{deal.package}</TableCell>
                  <TableCell>{deal.amount}</TableCell>
                  <TableCell>
                    <StatusBadge status={deal.payment} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default CrmFinancePage;
