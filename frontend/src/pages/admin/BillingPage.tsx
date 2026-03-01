import { useEffect, useMemo, useState } from "react";

import { changeBillingPlan, getBillingInvoices, getBillingPlans, getBillingSummary, type BillingInvoice, type BillingPlan, type BillingSummary } from "@/api/billing";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";


const Meter = ({ label, used, limit }: { label: string; used: number; limit: number }) => {
  const pct = Math.min(Math.round((used / Math.max(limit, 1)) * 100), 100);
  const tone = pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-yellow-500" : "bg-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm"><span>{label}</span><span>{used}/{limit}</span></div>
      <div className="h-2 rounded bg-muted"><div className={`h-2 rounded ${tone}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
};

const BillingPage = () => {
  const [data, setData] = useState<BillingSummary | null>(null);
  const [invoices, setInvoices] = useState<BillingInvoice[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);

  const reload = async () => {
    const [summary, invoiceItems, planItems] = await Promise.all([getBillingSummary(), getBillingInvoices(), getBillingPlans()]);
    setData(summary);
    setInvoices(invoiceItems);
    setPlans(planItems);
  };

  useEffect(() => {
    void reload();
  }, []);

  const alerts = useMemo(() => {
    if (!data) return [] as string[];
    const out: string[] = [];
    if (["suspended", "canceled", "past_due"].includes(data.subscription.status)) {
      out.push("Оплата просрочена или подписка неактивна — часть операций может быть заблокирована.");
    }
    const genLimit = Number(data.limits.generations_per_month ?? 0);
    const genUsed = Number(data.usage.docs_generated ?? 0);
    if (genLimit > 0 && genUsed >= genLimit) out.push("Лимит генераций документов исчерпан.");
    return out;
  }, [data]);

  const switchPlan = async (code: string) => {
    setBusyPlan(code);
    try {
      await changeBillingPlan(code);
      await reload();
    } finally {
      setBusyPlan(null);
    }
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Администрирование", to: "/admin" }, { label: "Биллинг" }]} />

      {alerts.length > 0 && (
        <Card className="border-red-500/50">
          <CardHeader><CardTitle>Предупреждения</CardTitle></CardHeader>
          <CardContent className="text-sm text-red-600 space-y-1">
            {alerts.map((item) => <div key={item}>• {item}</div>)}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle>Текущий тариф</CardTitle></CardHeader>
        <CardContent className="text-sm space-y-1">
          <div>План: {data?.plan.name ?? "—"}</div>
          <div>Статус: {data?.subscription.status ?? "—"}</div>
          <div>Период до: {data?.subscription.period_end ?? "—"}</div>
          <div>Grace period до: {data?.subscription.grace_until ?? "—"}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Лимиты и usage</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {data && <>
            <Meter label="Генерации / мес" used={Number(data.usage.docs_generated ?? 0)} limit={Number(data.limits.generations_per_month ?? 0)} />
            <Meter label="ЭДО исходящие / мес" used={Number(data.usage.edo_outgoing ?? 0)} limit={Number(data.limits.edo_outgoing_per_month ?? 0)} />
            <Meter label="S3 (GiB)" used={Math.round(Number(data.usage.s3_bytes_used ?? 0) / (1024 * 1024 * 1024))} limit={Number(data.limits.s3_gb_max ?? 0)} />
            <Meter label="Пользователи" used={0} limit={Number(data.limits.users_max ?? 0)} />
          </>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Возможности тарифа</CardTitle></CardHeader>
        <CardContent className="grid gap-2 text-sm md:grid-cols-2">
          {data && Object.entries(data.features).map(([feature, enabled]) => (
            <div key={feature} className="flex items-center justify-between rounded border px-3 py-2">
              <span>{feature}</span>
              <span className={enabled ? "text-emerald-600" : "text-muted-foreground"}>{enabled ? "включено" : "выключено"}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Тарифы</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {plans.map((plan) => (
            <div key={plan.code} className="space-y-2 rounded border p-3 text-sm">
              <div className="flex items-center justify-between">
                <div>{plan.name}</div>
                <Button size="sm" disabled={busyPlan === plan.code || data?.plan.code === plan.code} onClick={() => void switchPlan(plan.code)}>
                  {data?.plan.code === plan.code ? "Текущий" : "Сменить"}
                </Button>
              </div>
              <div className="grid gap-2 text-xs md:grid-cols-2">
                {Object.entries(plan.limits).slice(0, 6).map(([key, value]) => (
                  <div key={key} className="flex justify-between rounded bg-muted/40 px-2 py-1"><span>{key}</span><span>{String(value)}</span></div>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Счета</CardTitle></CardHeader>
        <CardContent className="text-sm space-y-1">
          {invoices.length === 0 && <div>Счета пока не выставлялись.</div>}
          {invoices.map((inv) => (
            <div key={inv.id} className="flex justify-between"><span>{inv.period_yyyymm} / {inv.status}</span><span>{inv.amount}</span></div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

export default BillingPage;
