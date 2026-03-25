import { useMemo, useState } from "react";

import {
  activateSubscription,
  changeBillingPlan,
  getBillingInvoices,
  getBillingPlans,
  getBillingSummary,
  markSubscriptionPaid,
  markSubscriptionPastDue,
  suspendSubscription,
  type BillingInvoice,
  type BillingPlan,
  type BillingSummary,
} from "@/api/billing";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const Meter = ({ label, used, limit }: { label: string; used: number; limit: number }) => {
  const pct = limit <= 0 ? 0 : Math.min(Math.round((used / Math.max(limit, 1)) * 100), 100);
  const tone = pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-yellow-500" : "bg-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm"><span>{label}</span><span>{used}/{limit || "∞"}</span></div>
      <div className="h-2 rounded bg-muted"><div className={`h-2 rounded ${tone}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
};

const BillingPage = () => {
  const { data, setData, loading, error, reload } = useAsyncResource({
    loader: async () => {
      const [summary, invoiceItems, planItems] = await Promise.all([getBillingSummary(), getBillingInvoices(), getBillingPlans()]);
      return {
        summary,
        invoices: invoiceItems,
        plans: planItems,
      };
    },
    initialData: {
      summary: null as BillingSummary | null,
      invoices: [] as BillingInvoice[],
      plans: [] as BillingPlan[],
    },
    errorMessage: "Не удалось загрузить биллинг",
  });
  const [busy, setBusy] = useState<string | null>(null);

  const alerts = useMemo(() => {
    if (!data.summary) return [] as string[];
    const out: string[] = [];
    if (["suspended", "canceled", "past_due"].includes(data.summary.subscription.status)) out.push("Подписка неактивна или в просрочке.");
    const genLimit = Number(data.summary.limits.max_generations_per_month ?? 0);
    const genUsed = Number(data.summary.usage.docs_generated ?? 0);
    if (genLimit > 0 && genUsed >= genLimit) out.push("Лимит генераций документов исчерпан.");
    return out;
  }, [data]);

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
      await reload();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Администрирование", to: "/admin" }, { label: "Биллинг" }]} />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка биллинга" /> : null}
      {!loading && !error && !data.summary ? (
        <EmptyState title="Биллинг временно недоступен" description="Данные тарифа и счетов появятся после инициализации billing context." />
      ) : null}

      {alerts.length > 0 && <Card className="border-red-500/50"><CardHeader><CardTitle>Предупреждения</CardTitle></CardHeader><CardContent className="text-sm text-red-600 space-y-1">{alerts.map((item) => <div key={item}>• {item}</div>)}</CardContent></Card>}

      <Card>
        <CardHeader><CardTitle>Тариф и статус</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div>План: <b>{data.summary?.plan.name ?? "—"}</b></div>
          <div>Статус: <b>{data.summary?.subscription.status ?? "—"}</b></div>
          <div>Период: {data.summary?.subscription.period_start ?? "—"} → {data.summary?.subscription.period_end ?? "—"}</div>
          <div>Grace до: {data.summary?.subscription.grace_until ?? "—"}</div>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button size="sm" disabled={busy === "past_due"} onClick={() => void run("past_due", () => markSubscriptionPastDue())}>Пометить неоплату</Button>
            <Button size="sm" variant="secondary" disabled={busy === "paid"} onClick={() => void run("paid", markSubscriptionPaid)}>Снять неоплату</Button>
            <Button size="sm" variant="outline" disabled={busy === "suspend"} onClick={() => void run("suspend", suspendSubscription)}>Приостановить</Button>
            <Button size="sm" variant="outline" disabled={busy === "activate"} onClick={() => void run("activate", activateSubscription)}>Активировать</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Usage</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {data && <>
            <Meter label="Генерации / мес" used={Number(data.summary?.usage.docs_generated ?? 0)} limit={Number(data.summary?.limits.max_generations_per_month ?? 0)} />
            <Meter label="ЭДО исходящие / мес" used={Number(data.summary?.usage.edo_outgoing ?? 0)} limit={Number(data.summary?.limits.edo_outgoing_per_month ?? 0)} />
            <Meter label="S3 bytes" used={Number(data.summary?.usage.s3_bytes_used ?? 0)} limit={Number(data.summary?.limits.max_s3_bytes ?? 0)} />
            <Meter label="Интеграции" used={0} limit={Number(data.summary?.limits.max_integrations ?? 0)} />
          </>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Тарифы</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {data.plans.map((plan) => (
            <div key={plan.code} className="space-y-2 rounded border p-3 text-sm">
              <div className="flex items-center justify-between">
                <div>{plan.name}</div>
                <Button size="sm" disabled={busy === plan.code || data.summary?.plan.code === plan.code} onClick={() => void run(plan.code, () => changeBillingPlan(plan.code))}>{data.summary?.plan.code === plan.code ? "Текущий" : "Сменить"}</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Счета</CardTitle></CardHeader>
        <CardContent className="text-sm space-y-1">
          {data.invoices.length === 0 && <div>Счета пока не выставлялись.</div>}
          {data.invoices.map((inv) => <div key={inv.id} className="flex justify-between"><span>{inv.period_yyyymm} / {inv.status}</span><span>{inv.amount}</span></div>)}
        </CardContent>
      </Card>
    </div>
  );
};

export default BillingPage;
