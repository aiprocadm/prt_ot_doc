import { useEffect, useMemo, useState } from "react";

import { opsApi } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const AuditPrepPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [snapshot, setSnapshot] = useState<{ inspections: any[]; prescriptions: any[]; overdueTasks: any[] }>({ inspections: [], prescriptions: [], overdueTasks: [] });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await opsApi.getAuditPrepSnapshot());
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить подготовку к проверкам" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const packages = useMemo(() => {
    const byAuthority = new Map<string, { name: string; inspections: number; openPrescriptions: number; blockers: number; next: string | null }>();
    snapshot.inspections.forEach((inspection) => {
      const key = inspection.authority || inspection.inspection_type || "Внутренний аудит";
      const existing = byAuthority.get(key) ?? { name: key, inspections: 0, openPrescriptions: 0, blockers: 0, next: null };
      existing.inspections += 1;
      if (!existing.next || (inspection.scheduled_at && inspection.scheduled_at < existing.next)) existing.next = inspection.scheduled_at;
      byAuthority.set(key, existing);
    });
    snapshot.prescriptions.forEach((prescription) => {
      const authorityKey = Array.from(byAuthority.keys())[0] ?? "Общий контур";
      const existing = byAuthority.get(authorityKey) ?? { name: authorityKey, inspections: 0, openPrescriptions: 0, blockers: 0, next: null };
      if (!["closed", "resolved", "done"].includes(String(prescription.status).toLowerCase())) existing.openPrescriptions += 1;
      byAuthority.set(authorityKey, existing);
    });
    snapshot.overdueTasks.forEach(() => {
      const authorityKey = Array.from(byAuthority.keys())[0] ?? "Общий контур";
      const existing = byAuthority.get(authorityKey) ?? { name: authorityKey, inspections: 0, openPrescriptions: 0, blockers: 0, next: null };
      existing.blockers += 1;
      byAuthority.set(authorityKey, existing);
    });
    return Array.from(byAuthority.values()).map((entry) => {
      const denominator = Math.max(1, entry.inspections + entry.openPrescriptions + entry.blockers);
      const readiness = Math.max(0, Math.round((entry.inspections / denominator) * 100));
      return { ...entry, readiness };
    });
  }, [snapshot]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Подготовка к проверке" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить пакетную сводку</Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Пакеты документов</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Сбор контуров подготовки к проверке" /> : null}
          {!loading && !error && packages.length === 0 ? (
            <EmptyState title="Нет контуров проверки" description="Инспекции и связанные blockers ещё не зарегистрированы." />
          ) : null}
          {!loading && !error && packages.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Пакет</TableHead>
                  <TableHead>Готовность</TableHead>
                  <TableHead>Пробелы</TableHead>
                  <TableHead>Дата проверки</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {packages.map((pkg) => (
                  <TableRow key={pkg.name}>
                    <TableCell className="font-medium">{pkg.name}</TableCell>
                    <TableCell>{pkg.readiness}%</TableCell>
                    <TableCell>{pkg.openPrescriptions} предписаний · {pkg.blockers} blockers</TableCell>
                    <TableCell>{formatDate(pkg.next) || "—"}</TableCell>
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

export default AuditPrepPage;
