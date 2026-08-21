import { useCallback, useEffect, useMemo, useState } from "react";

import { crmFinanceApi, type CrmFinanceSnapshot } from "@/api/crmFinance";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCompaniesStore } from "@/stores/companies";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const formatCurrency = (
  amount: number | null | undefined,
  currency: string | null | undefined,
) => {
  if (amount == null) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: currency || "RUB",
    maximumFractionDigits: 0,
  }).format(amount);
};

const resolvePaymentStatus = (statuses: string[]) => {
  const normalized = statuses.map((status) => status.toLowerCase());
  if (
    normalized.some((status) => status === "overdue" || status === "past_due")
  )
    return "overdue";
  if (normalized.length > 0 && normalized.every((status) => status === "paid"))
    return "ready";
  if (normalized.some((status) => status === "issued" || status === "draft"))
    return "processing";
  return normalized[0] || "draft";
};

const CrmFinancePage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [snapshot, setSnapshot] = useState<CrmFinanceSnapshot>({
    contracts: [],
    orders: [],
    invoices: [],
    billing: null,
  });
  const { items: companies, list: listCompanies } = useCompaniesStore();

  const companyMap = useMemo(
    () => new Map(companies.map((company) => [company.id, company.name])),
    [companies],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await crmFinanceApi.getSnapshot();
      setSnapshot(data);
    } catch (err) {
      setError(
        (err as ApiError) ?? {
          message: "Не удалось загрузить CRM/финансовые данные",
        },
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    listCompanies({ page_size: 100 }).catch(() => undefined);
  }, [listCompanies, load]);

  const rows = useMemo(() => {
    const invoiceByContract = new Map<string, typeof snapshot.invoices>();
    const orderByContract = new Map<string, typeof snapshot.orders>();

    snapshot.invoices.forEach((invoice) => {
      invoiceByContract.set(invoice.contract_id, [
        ...(invoiceByContract.get(invoice.contract_id) ?? []),
        invoice,
      ]);
    });
    snapshot.orders.forEach((order) => {
      orderByContract.set(order.contract_id, [
        ...(orderByContract.get(order.contract_id) ?? []),
        order,
      ]);
    });

    return snapshot.contracts.map((contract) => {
      const contractInvoices = invoiceByContract.get(contract.id) ?? [];
      const contractOrders = orderByContract.get(contract.id) ?? [];
      const paymentStatus = resolvePaymentStatus(
        contractInvoices.map((invoice) => invoice.status),
      );
      const billedAmount = contractInvoices.reduce(
        (sum, invoice) => sum + (invoice.total_amount ?? 0),
        0,
      );
      const searchBlob = [
        contract.contract_number,
        contract.title,
        contract.counterparty_name,
        companyMap.get(contract.company_id),
        ...contractOrders.map((order) => order.order_number),
        ...contractInvoices.map((invoice) => invoice.invoice_number),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return {
        id: contract.id,
        dealLabel: contract.contract_number || contract.id.slice(0, 8),
        client:
          companyMap.get(contract.company_id) || contract.counterparty_name,
        packageName: contract.title,
        amount: formatCurrency(contract.total_amount, contract.currency),
        billedAmount: formatCurrency(billedAmount, contract.currency),
        paymentStatus,
        ordersCount: contractOrders.length,
        invoicesCount: contractInvoices.length,
        validUntil: contract.valid_until,
        contractStatus: contract.status,
        searchBlob,
      };
    });
  }, [companyMap, snapshot]);

  const filteredRows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((row) => row.searchBlob.includes(normalized));
  }, [query, rows]);

  const totals = useMemo(() => {
    const contractAmount = snapshot.contracts.reduce(
      (sum, contract) => sum + (contract.total_amount ?? 0),
      0,
    );
    const invoiceAmount = snapshot.invoices.reduce(
      (sum, invoice) => sum + (invoice.total_amount ?? 0),
      0,
    );
    const paidInvoices = snapshot.invoices.filter(
      (invoice) => invoice.status.toLowerCase() === "paid",
    ).length;
    return { contractAmount, invoiceAmount, paidInvoices };
  }, [snapshot.contracts, snapshot.invoices]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="CRM / Финансы"
        description="Реальные договоры, заказы, счета и статус биллинга в рамках тенанта вместо демо-таблицы."
        actions={
          snapshot.billing?.plan?.name ? (
            <Badge variant="secondary">
              План: {snapshot.billing.plan.name}
            </Badge>
          ) : null
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Договоров в работе
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : snapshot.contracts.length}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Общая сумма договоров
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : formatCurrency(totals.contractAmount, "RUB")}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Выставлено по счетам
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading ? "—" : formatCurrency(totals.invoiceAmount, "RUB")}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Оплаченные счета
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold">
              {loading ? "—" : totals.paidInvoices}
            </div>
            {snapshot.billing?.subscription_status ? (
              <StatusBadge status={snapshot.billing.subscription_status} />
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Активные сделки и оплаты</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            placeholder="Поиск по договору, клиенту, номеру заказа или счета"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? (
            <LoadingScreen label="Загрузка CRM/финансовых данных" />
          ) : null}
          {!loading && !error && filteredRows.length === 0 ? (
            <EmptyState
              title="Сделки не найдены"
              description={
                query
                  ? "Попробуйте изменить поисковый запрос."
                  : "В этом tenant пока нет договоров и связанных счетов."
              }
            />
          ) : null}

          {!loading && !error && filteredRows.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Клиент</TableHead>
                  <TableHead>Пакет / договор</TableHead>
                  <TableHead>Сумма</TableHead>
                  {/* BIZ-60 волна 3: два узких счётчика в одной колонке —
                      восьмая колонка выводила экран за лимит разд. 59.2, а
                      оба числа читаются вместе: это объём документов сделки. */}
                  <TableHead>Счета / заказы</TableHead>
                  <TableHead>Оплата</TableHead>
                  <TableHead>Срок действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-medium">
                      {row.dealLabel}
                    </TableCell>
                    <TableCell>{row.client}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div>{row.packageName}</div>
                        <div className="text-xs text-muted-foreground">
                          Статус договора: {row.contractStatus}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div>{row.amount}</div>
                        <div className="text-xs text-muted-foreground">
                          Выставлено: {row.billedAmount}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      {row.invoicesCount} / {row.ordersCount}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.paymentStatus} />
                    </TableCell>
                    <TableCell>{formatDate(row.validUntil) || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CrmFinancePage;
