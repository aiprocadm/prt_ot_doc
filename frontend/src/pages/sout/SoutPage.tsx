import { useEffect, useState } from "react";

import {
  soutApi,
  type SoutCampaign,
  type SoutCampaignReport,
} from "@/api/sout";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

// ── Class-of-conditions label (ФЗ-426 ст. 14) ───────────────────────────────

const CLASS_LABELS: Record<string, string> = {
  optimal: "1 — оптимальный",
  acceptable: "2 — допустимый",
  harmful_3_1: "3.1 — вредный",
  harmful_3_2: "3.2 — вредный",
  harmful_3_3: "3.3 — вредный",
  harmful_3_4: "3.4 — вредный",
  dangerous: "4 — опасный",
};

const GUARANTEE_LABELS: Record<string, string> = {
  additional_leave: "Доп. отпуск",
  extra_pay: "Повышенная оплата",
  reduced_hours: "Сокращённая неделя",
  milk: "Молоко / ЛПП",
  early_pension: "Досрочная пенсия",
  medical_exam: "Медосмотр",
};

const classLabel = (code?: string | null): string =>
  code ? (CLASS_LABELS[code] ?? code) : "—";

// ── Campaign list panel ─────────────────────────────────────────────────────

interface CampaignListProps {
  selected: SoutCampaign | null;
  onSelect: (c: SoutCampaign) => void;
}

const CampaignList = ({ selected, onSelect }: CampaignListProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<SoutCampaign[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await soutApi.list();
      setItems(page.items);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить кампании СОУТ" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Кампании СОУТ</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка кампаний" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Кампании СОУТ ещё не созданы." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Название</TableHead>
                <TableHead>Отчёт №</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((c) => (
                <TableRow
                  key={c.id}
                  className={`cursor-pointer ${selected?.id === c.id ? "bg-muted" : ""}`}
                  onClick={() => onSelect(c)}
                >
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-muted-foreground">{c.report_number ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{c.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Report panel (workplaces + factors + guarantees) ────────────────────────

interface ReportPanelProps {
  campaign: SoutCampaign;
}

const ReportPanel = ({ campaign }: ReportPanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [report, setReport] = useState<SoutCampaignReport | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await soutApi.getReport(campaign.id);
      setReport(data);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить отчёт СОУТ" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [campaign.id]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Рабочие места — {campaign.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка отчёта" /> : null}
        {!loading && !error && report !== null && report.workplaces.length === 0 ? (
          <EmptyState title="Нет данных" description="Рабочие места ещё не внесены." />
        ) : null}
        {!loading && !error && report !== null && report.workplaces.length > 0 ? (
          <div className="space-y-4">
            {report.workplaces.map(({ workplace, factors, guarantees }) => (
              <div key={workplace.id} className="rounded-md border border-border p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">
                    {workplace.workplace_code} · {workplace.position_name}
                  </p>
                  <span className="flex items-center gap-2">
                    <Badge variant="secondary">{classLabel(workplace.assessed_class)}</Badge>
                    {workplace.is_reassessment_due ? (
                      <Badge variant="destructive" className="text-xs">
                        Переоценка просрочена
                      </Badge>
                    ) : null}
                  </span>
                </div>
                {workplace.next_assessment_date ? (
                  <p className="text-xs text-muted-foreground">
                    Следующая оценка: {formatDate(workplace.next_assessment_date)}
                  </p>
                ) : null}
                {factors.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Фактор</TableHead>
                        <TableHead>Класс</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {factors.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell className="font-medium">{f.name}</TableCell>
                          <TableCell className="text-muted-foreground">
                            {classLabel(f.measured_class)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-xs text-muted-foreground">Вредные факторы не выявлены.</p>
                )}
                {guarantees.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {guarantees.map((g) => (
                      <Badge key={g.id} variant="outline">
                        {GUARANTEE_LABELS[g.kind] ?? g.kind}
                        {g.detail ? `: ${g.detail}` : ""}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Page ────────────────────────────────────────────────────────────────────

const SoutPage = () => {
  const [selectedCampaign, setSelectedCampaign] = useState<SoutCampaign | null>(null);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="СОУТ"
        description="Специальная оценка условий труда: кампании, классы условий, гарантии и компенсации."
      />
      <CampaignList selected={selectedCampaign} onSelect={setSelectedCampaign} />
      {selectedCampaign !== null ? <ReportPanel campaign={selectedCampaign} /> : null}
    </div>
  );
};

export default SoutPage;
