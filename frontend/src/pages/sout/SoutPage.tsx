import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  soutApi,
  type NormSuggestions as NormSuggestionsData,
  type SoutCampaign,
  type SoutCampaignReport,
  type SoutClassHistoryEntry,
  type SoutDeclarationPreview,
} from "@/api/sout";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

// ── Class-history (lazy, per workplace) ─────────────────────────────────────

interface ClassHistoryProps {
  workplaceId: string;
}

const ClassHistory = ({ workplaceId }: ClassHistoryProps) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [entries, setEntries] = useState<SoutClassHistoryEntry[] | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && entries === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        setEntries(await soutApi.listClassHistory(workplaceId));
      } catch (err) {
        setError((err as ApiError) ?? { message: "Не удалось загрузить историю класса" });
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => void toggle()}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        {open ? "Скрыть историю класса" : "История изменения класса"}
      </button>
      {open ? (
        <div className="space-y-1">
          <ErrorState error={error ?? undefined} onRetry={() => void toggle()} />
          {loading ? <LoadingScreen label="Загрузка истории" /> : null}
          {!loading && !error && entries !== null && entries.length === 0 ? (
            <p className="text-xs text-muted-foreground">Изменений класса не зафиксировано.</p>
          ) : null}
          {!loading && !error && entries !== null && entries.length > 0 ? (
            <ul className="space-y-1 text-xs">
              {entries.map((e) => (
                <li key={e.id} className="flex items-center gap-2">
                  <span className="text-muted-foreground">{formatDate(e.changed_at)}</span>
                  <span>
                    {classLabel(e.old_class)} → {classLabel(e.new_class)}
                  </span>
                  {e.is_worsening ? (
                    <Badge variant="destructive" className="text-xs">
                      Ухудшение
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

// ── Norm suggestions (lazy, per workplace) ──────────────────────────────────

interface NormSuggestionsProps {
  workplaceId: string;
}

const NormSuggestionsSection = ({ workplaceId }: NormSuggestionsProps) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [data, setData] = useState<NormSuggestionsData | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && data === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        setData(await soutApi.getNormSuggestions(workplaceId));
      } catch (err) {
        setError((err as ApiError) ?? { message: "Не удалось загрузить предложения норм" });
      } finally {
        setLoading(false);
      }
    }
  };

  const isEmpty = data !== null && data.ppe.length === 0 && data.medical.length === 0;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => void toggle()}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        {open ? "Скрыть предложения норм" : "Предложения норм"}
      </button>
      {open ? (
        <div className="space-y-2">
          <ErrorState error={error ?? undefined} onRetry={() => void toggle()} />
          {loading ? <LoadingScreen label="Загрузка предложений" /> : null}
          {!loading && !error && isEmpty ? (
            <p className="text-xs text-muted-foreground">Предложений норм нет.</p>
          ) : null}
          {!loading && !error && data !== null && data.ppe.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium">СИЗ</p>
              <ul className="space-y-1 text-xs">
                {data.ppe.map((p) => (
                  <li key={`ppe-${p.hazard_id}`} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{p.hazard_title || p.factor_name}</span>
                    <span className="text-muted-foreground">{p.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {!loading && !error && data !== null && data.medical.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium">Медосмотры</p>
              <ul className="space-y-1 text-xs">
                {data.medical.map((m) => (
                  <li key={`med-${m.exam_kind}`} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{m.exam_kind}</span>
                    <span className="text-muted-foreground">{m.periodicity_months} мес</span>
                    <span className="text-muted-foreground">{m.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {!loading && !error && !isEmpty && data !== null ? (
            <p className="text-xs italic text-muted-foreground">
              Подтвердите в разделе СИЗ / Медосмотры
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

// ── Link controls (set position_id / hazard_id) ─────────────────────────────

interface LinkInputProps {
  label: string;
  buttonLabel: string;
  onSubmit: (value: string) => Promise<void>;
}

const LinkInput = ({ label, buttonLabel, onSubmit }: LinkInputProps) => {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submit = async () => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(trimmed);
      setValue("");
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось сохранить связь" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={label}
          className="h-8 max-w-xs text-xs"
        />
        <Button type="button" size="sm" disabled={busy} onClick={() => void submit()}>
          {buttonLabel}
        </Button>
      </div>
      <ErrorState error={error ?? undefined} />
    </div>
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
  const [declaration, setDeclaration] = useState<SoutDeclarationPreview | null>(null);

  useEffect(() => {
    let active = true;
    void soutApi
      .getDeclaration(campaign.id)
      .then((d) => { if (active) setDeclaration(d); })
      .catch(() => { if (active) setDeclaration(null); });
    return () => { active = false; };
  }, [campaign.id]);

  const handleDeclarationDownload = async (fmt: "docx" | "pdf") => {
    try {
      await soutApi.downloadDeclaration(campaign.id, fmt, campaign.name);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(
        fmt === "pdf" && status === 503
          ? "PDF-конвертер недоступен, скачайте DOCX"
          : "Не удалось скачать документ",
      );
    }
  };

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

  const handleSummaryDownload = async (fmt: "docx" | "pdf") => {
    try {
      await soutApi.downloadSummary(campaign.id, fmt, campaign.name);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(
        fmt === "pdf" && status === 503
          ? "PDF-конвертер недоступен, скачайте DOCX"
          : "Не удалось скачать документ",
      );
    }
  };

  const handleCardDownload = async (workplaceId: string, code: string, fmt: "docx" | "pdf") => {
    try {
      await soutApi.downloadCard(workplaceId, fmt, code);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(
        fmt === "pdf" && status === 503
          ? "PDF-конвертер недоступен, скачайте DOCX"
          : "Не удалось скачать документ",
      );
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Рабочие места — {campaign.name}</CardTitle>
          <span className="flex gap-1">
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleSummaryDownload("docx")}>
              Сводная DOCX
            </Button>
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleSummaryDownload("pdf")}>
              Сводная PDF
            </Button>
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleDeclarationDownload("docx")}>
              Декларация DOCX
            </Button>
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleDeclarationDownload("pdf")}>
              Декларация PDF
            </Button>
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {declaration !== null ? (
          <div className="rounded-md border border-border p-3 text-sm" data-testid="sout-declaration-summary">
            <p className="font-medium">Декларация соответствия (класс 1-2)</p>
            <p className="text-muted-foreground">
              Подлежат декларированию: {declaration.eligible_count} · не подлежат: {declaration.ineligible_count}
            </p>
            {declaration.ineligible.length > 0 ? (
              <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
                {declaration.ineligible.map((r, i) => (
                  <li key={`${r.workplace_code}-${i}`}>
                    {r.workplace_code} · {r.position_name} — {r.ineligible_reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
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
                    <Button type="button" size="sm" variant="outline"
                      onClick={() => void handleCardDownload(workplace.id, workplace.workplace_code, "docx")}>
                      Карта DOCX
                    </Button>
                    <Button type="button" size="sm" variant="outline"
                      onClick={() => void handleCardDownload(workplace.id, workplace.workplace_code, "pdf")}>
                      Карта PDF
                    </Button>
                  </span>
                </div>
                {workplace.next_assessment_date ? (
                  <p className="text-xs text-muted-foreground">
                    Следующая оценка: {formatDate(workplace.next_assessment_date)}
                  </p>
                ) : null}
                <LinkInput
                  label="ID должности"
                  buttonLabel="Привязать должность"
                  onSubmit={async (positionId) => {
                    await soutApi.linkWorkplacePosition(workplace.id, positionId);
                    await load();
                  }}
                />
                {factors.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Фактор</TableHead>
                        <TableHead>Класс</TableHead>
                        <TableHead>Опасность</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {factors.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell className="font-medium">{f.name}</TableCell>
                          <TableCell className="text-muted-foreground">
                            {classLabel(f.measured_class)}
                          </TableCell>
                          <TableCell>
                            <LinkInput
                              label="ID опасности"
                              buttonLabel="Привязать"
                              onSubmit={async (hazardId) => {
                                await soutApi.linkFactorHazard(f.id, hazardId);
                                await load();
                              }}
                            />
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
                <ClassHistory workplaceId={workplace.id} />
                <NormSuggestionsSection workplaceId={workplace.id} />
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
