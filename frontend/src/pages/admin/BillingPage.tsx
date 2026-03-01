import { useEffect, useState } from "react";

import { getBillingSummary, type BillingSummary } from "@/api/billing";
import { Breadcrumb } from "@/components/ui/breadcrumb";
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

  useEffect(() => {
    void getBillingSummary().then(setData);
  }, []);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Администрирование", to: "/admin" }, { label: "Биллинг" }]} />
      <Card>
        <CardHeader><CardTitle>Текущий тариф</CardTitle></CardHeader>
        <CardContent className="text-sm space-y-1">
          <div>План: {data?.plan.name ?? "—"}</div>
          <div>Статус: {data?.subscription.status ?? "—"}</div>
          <div>Период до: {data?.subscription.period_end ?? "—"}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Лимиты и usage</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {data && <>
            <Meter label="Генерации / мес" used={Number(data.usage.docs_generated ?? 0)} limit={Number(data.limits.generations_per_month ?? 0)} />
            <Meter label="ЭДО исходящие / мес" used={Number(data.usage.edo_outgoing ?? 0)} limit={Number(data.limits.edo_outgoing_per_month ?? 0)} />
          </>}
        </CardContent>
      </Card>
    </div>
  );
};

export default BillingPage;
