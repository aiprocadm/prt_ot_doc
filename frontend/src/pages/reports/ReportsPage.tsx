import { useCallback, useEffect, useState } from "react";

import { reportsApi } from "@/api/reports";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAbility } from "@/permissions/useAbility";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import { toast } from "sonner";

type KpiPayload = {
  risks_high: number;
  trainings_overdue: number;
  ppe_issues_month: number;
  incidents_open: number;
  prescriptions_overdue: number;
};

const today = () => new Date().toISOString().slice(0, 10);
const monthAgo = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
};

const ReportsPage = () => {
  const ability = useAbility();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [kpi, setKpi] = useState<KpiPayload | null>(null);
  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo] = useState(today);
  const [exporting, setExporting] = useState(false);
  const [lastExportId, setLastExportId] = useState<string | null>(null);
  const canExportReports = ability.can(PERMISSIONS.DOCUMENT_EXPORT) || ability.can(PERMISSIONS.REPORTS_VIEW);

  const loadKpi = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await reportsApi.getKpi<KpiPayload>({ date_from: dateFrom, date_to: dateTo });
      setKpi(data);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить KPI" });
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    void loadKpi();
  }, [loadKpi]);

  const exportReport = async (format: "xlsx" | "pdf") => {
    setExporting(true);
    try {
      const data = await reportsApi.queueExport(format, dateFrom, dateTo);
      setLastExportId(data.id);
      toast.success(`Экспорт поставлен в очередь: ${data.id.slice(0, 8)}`);
    } catch {
      toast.error("Не удалось создать задачу экспорта");
    } finally {
      setExporting(false);
    }
  };

  const cards = [
    { label: "Высокие риски", value: kpi?.risks_high ?? 0, href: "/risk" },
    { label: "Просроченные обучения", value: kpi?.trainings_overdue ?? 0, href: "/training" },
    { label: "Выдачи СИЗ за период", value: kpi?.ppe_issues_month ?? 0, href: "/ppe" },
    { label: "Открытые инциденты", value: kpi?.incidents_open ?? 0, href: "/incidents" },
    { label: "Просроченные предписания", value: kpi?.prescriptions_overdue ?? 0, href: "/inspections" }
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Отчёты" }]} />
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={exporting || !canExportReports}
            title={canExportReports ? undefined : "Недостаточно прав для экспорта"}
            onClick={() => void exportReport("xlsx")}
          >
            {exporting ? "Экспорт…" : "XLSX"}
          </Button>
          <Button
            variant="outline"
            disabled={exporting || !canExportReports}
            title={canExportReports ? undefined : "Недостаточно прав для экспорта"}
            onClick={() => void exportReport("pdf")}
          >
            PDF
          </Button>
        </div>
      </div>

      {/* Period filter */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="space-y-1.5">
            <Label htmlFor="rpt-from">С</Label>
            <Input id="rpt-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rpt-to">По</Label>
            <Input id="rpt-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <Button onClick={() => void loadKpi()}>Применить</Button>
        </CardContent>
      </Card>

      <ErrorState error={error ?? undefined} onRetry={loadKpi} />
      {loading ? <LoadingScreen label="Загрузка показателей" /> : null}

      {lastExportId ? (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">
            Последний export job: <a href="/exports" className="text-primary underline">{lastExportId}</a>. Отслеживание статуса и повторный запуск доступны в Export Center.
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((item) => (
          <Card key={item.label} className="transition hover:shadow-md">
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">{item.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold">{loading ? "—" : item.value}</div>
              {item.href && (
                <a href={item.href} className="mt-2 inline-block text-xs text-primary underline">
                  Подробнее →
                </a>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default ReportsPage;
