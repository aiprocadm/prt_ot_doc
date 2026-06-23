import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { fetchAllPersons, workPermitsApi, type PersonOption } from "@/api/workPermits";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { BriefingPanel } from "@/features/work-permits/BriefingPanel";
import { BrigadeMembersPanel } from "@/features/work-permits/BrigadeMembersPanel";
import { ClosingPanel } from "@/features/work-permits/ClosingPanel";
import { DailyAdmissionPanel } from "@/features/work-permits/DailyAdmissionPanel";
import { PrintButtons } from "@/features/work-permits/PrintButtons";
import { ReadinessPanel } from "@/features/work-permits/ReadinessPanel";
import { SignaturesPanel, type SignerRow } from "@/features/work-permits/SignaturesPanel";
import { WorkPermitEventsTimeline } from "@/features/work-permits/WorkPermitEventsTimeline";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import {
  MEMBER_ROLE_LABELS,
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  VENTILATION_LABELS,
  GAS_PARAMETER_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
  RESPIRATORY_PPE_LABELS,
  ELECTRICAL_MEASURES_LABELS,
  VOLTAGE_CONDITION_LABELS,
  labelOf,
} from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ReadinessReportDto, WorkPermitClosingSummaryDto, WorkPermitDto, WorkPermitEventDto, WorkPermitSignatureDto } from "@/types/dto/workPermits";

// Actions available per status (excluding "Продлить" which needs a date input)
const ACTIONS_BY_STATUS: Record<
  string,
  Array<{ name: "issue" | "suspend" | "resume" | "close" | "cancel"; label: string }>
> = {
  draft: [
    { name: "issue", label: "Выдать" },
    { name: "cancel", label: "Отменить" },
  ],
  issued: [
    { name: "suspend", label: "Приостановить" },
    { name: "close", label: "Закрыть" },
    { name: "cancel", label: "Отменить" },
  ],
  suspended: [
    { name: "resume", label: "Возобновить" },
    { name: "close", label: "Закрыть" },
    { name: "cancel", label: "Отменить" },
  ],
};

// Typed helper to safely extract error response body from axios errors
function getResponseData(e: unknown): Record<string, unknown> | null {
  if (e && typeof e === "object" && "response" in e) {
    const resp = (e as { response?: { data?: unknown } }).response;
    if (resp && typeof resp.data === "object" && resp.data !== null) {
      return resp.data as Record<string, unknown>;
    }
  }
  return null;
}

// Section display helper — renders only when value is non-empty
function Section({ title, value }: { title: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="text-sm whitespace-pre-wrap">{value}</div>
    </div>
  );
}

export default function WorkPermitDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  const [persons, setPersons] = useState<PersonOption[]>([]);
  const [readiness, setReadiness] = useState<ReadinessReportDto | null>(null);
  const [events, setEvents] = useState<WorkPermitEventDto[]>([]);
  const [signatures, setSignatures] = useState<WorkPermitSignatureDto[]>([]);
  const [closingSummary, setClosingSummary] = useState<WorkPermitClosingSummaryDto | null>(null);

  // Extend dialog state
  const [extendOpen, setExtendOpen] = useState(false);
  const [extendDate, setExtendDate] = useState("");
  const [extending, setExtending] = useState(false);

  // Main permit loader
  const loader = useCallback(() => workPermitsApi.get(id), [id]);
  const { data: wp, loading, error, reload } = useAsyncResource<WorkPermitDto | null>({
    loader,
    initialData: null,
    errorMessage: "Не удалось загрузить наряд",
  });

  // Fetch person list once
  useEffect(() => {
    fetchAllPersons().then(setPersons).catch(() => undefined);
  }, []);

  // Refresh side panels (readiness + events + signatures + closing) when permit changes
  const refreshSide = useCallback(() => {
    workPermitsApi.readiness(id).then(setReadiness).catch(() => undefined);
    workPermitsApi.events(id).then(setEvents).catch(() => undefined);
    workPermitsApi.listSignatures(id).then(setSignatures).catch(() => undefined);
    workPermitsApi.getClosing(id).then(setClosingSummary).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    if (wp) refreshSide();
  }, [wp, refreshSide]);

  // Build personId → name lookup
  const nameOf = useMemo(() => {
    const m = new Map(persons.map((p) => [p.id, p.label]));
    return (pid: string) => m.get(pid) ?? pid;
  }, [persons]);

  if (loading) return <LoadingScreen label="Загрузка наряда" />;
  if (error || !wp) return <ErrorState error={error ?? undefined} onRetry={() => void reload()} />;

  // Run a lifecycle action; handle WORK_PERMIT_BLOCKED (409) and generic errors
  const runAction = async (name: "issue" | "suspend" | "resume" | "close" | "cancel") => {
    try {
      await workPermitsApi.action(wp.id, name);
      toast.success("Готово");
      void reload();
    } catch (e: unknown) {
      const data = getResponseData(e);
      if (data?.code === "WORK_PERMIT_BLOCKED") {
        toast.error("Бригада не готова — наряд нельзя выдать. Проверьте панель готовности.");
        refreshSide();
      } else if (data?.code === "WORK_PERMIT_CLOSING_INCOMPLETE") {
        const missing = Array.isArray(data.missing)
          ? (data.missing as string[])
          : [];
        const { CLOSING_MISSING_LABELS } = await import("@/lib/workPermitVocab");
        const reasons = missing.map((k) => CLOSING_MISSING_LABELS[k] ?? k).join("; ");
        toast.error(`Не выполнены условия закрытия: ${reasons || "проверьте панель закрытия"}`);
        refreshSide();
      } else if (data?.code === "WORK_PERMIT_TRANSITION_INVALID") {
        toast.error("Действие недоступно в текущем статусе");
      } else {
        toast.error("Не удалось выполнить действие");
      }
      void reload();
    }
  };

  // Run extend
  const runExtend = async () => {
    if (!extendDate) {
      toast.error("Укажите новую дату окончания");
      return;
    }
    setExtending(true);
    try {
      await workPermitsApi.extend(wp.id, new Date(extendDate).toISOString());
      toast.success("Срок продлён");
      setExtendOpen(false);
      setExtendDate("");
      void reload();
    } catch {
      toast.error("Не удалось продлить наряд");
    } finally {
      setExtending(false);
    }
  };

  // Delete draft
  const handleDelete = async () => {
    try {
      await workPermitsApi.remove(wp.id);
      toast.success("Наряд удалён");
      void navigate("/work-permits");
    } catch {
      toast.error("Не удалось удалить наряд");
    }
  };

  const RESP_ROLES = new Set(["issuer", "supervisor", "admitter", "foreman"]);
  const responsibleSigners: SignerRow[] = wp.members
    .filter((m) => RESP_ROLES.has(m.role))
    .map((m) => ({ personId: m.person_id, name: nameOf(m.person_id), roleLabel: labelOf(MEMBER_ROLE_LABELS, m.role) }));
  const permitSignatures = signatures.filter((s) => s.stream === "permit");

  const CLOSING_ROLES = new Set(["foreman", "supervisor", "admitter"]);
  const closingSigners: SignerRow[] = wp.members
    .filter((m) => CLOSING_ROLES.has(m.role))
    .map((m) => ({ personId: m.person_id, name: nameOf(m.person_id), roleLabel: labelOf(MEMBER_ROLE_LABELS, m.role) }));

  const signPermit = async (personId: string, mode: "attested" | "code") => {
    const res = await workPermitsApi.createPermitSignature(wp.id, { person_id: personId, mode });
    if (mode === "code" && res.confirm_code) toast.success(`Код для подписанта: ${res.confirm_code}`);
    refreshSide();
  };
  const confirmSign = async (requestId: string, code: string) => {
    await workPermitsApi.confirmSignatureCode(requestId, code);
    toast.success("Подпись подтверждена");
    refreshSide();
  };

  // Скачать печатный бланк (DOCX всегда; PDF best-effort — 503 если нет конвертера)
  const handleDownload = async (fmt: "docx" | "pdf") => {
    try {
      await workPermitsApi.downloadPrint(wp.id, fmt, wp.number ?? undefined);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (fmt === "pdf" && status === 503) {
        toast.error("PDF-конвертер недоступен, скачайте DOCX");
      } else {
        toast.error("Не удалось скачать документ");
      }
    }
  };

  const safetySystemsText =
    (wp.safety_systems ?? []).map((c) => SAFETY_SYSTEM_LABELS[c] ?? c).join(", ") || null;

  return (
    <div className="space-y-5">
      <Link to="/work-permits" className="text-sm text-muted-foreground hover:underline">
        ← Наряды-допуски
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium flex items-center gap-2">
            Наряд {wp.number ?? "(без номера)"}
            <StatusBadge status={wp.status} />
          </h1>
          <p className="text-sm text-muted-foreground">
            {labelOf(WORK_TYPE_LABELS, wp.work_type)} · {wp.zone_text}
            {wp.subdivision_text ? ` · ${wp.subdivision_text}` : ""}
          </p>
        </div>

        {/* Action buttons — manage-gated */}
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="flex flex-wrap gap-2 justify-end">
            {wp.status === "draft" && (
              <WorkPermitFormDialog
                trigger={<Button variant="outline">Изменить</Button>}
                initialData={wp}
                onSubmitted={() => void reload()}
              />
            )}

            {(ACTIONS_BY_STATUS[wp.status] ?? []).map((a) => (
              <Button
                key={a.name}
                variant="outline"
                onClick={() => void runAction(a.name)}
              >
                {a.label}
              </Button>
            ))}

            {/* Продлить — only for issued */}
            {wp.status === "issued" && !extendOpen && (
              <Button variant="outline" onClick={() => setExtendOpen(true)}>
                Продлить
              </Button>
            )}
            {wp.status === "issued" && extendOpen && (
              <div className="flex items-center gap-2">
                <input
                  type="datetime-local"
                  className="h-9 rounded-md border px-2 text-sm"
                  value={extendDate}
                  onChange={(e) => setExtendDate(e.target.value)}
                />
                <Button
                  size="sm"
                  disabled={extending || !extendDate}
                  onClick={() => void runExtend()}
                >
                  {extending ? "..." : "Ок"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => { setExtendOpen(false); setExtendDate(""); }}
                >
                  Отмена
                </Button>
              </div>
            )}

            {wp.status === "draft" && (
              <Button variant="outline" onClick={() => void handleDelete()}>
                Удалить
              </Button>
            )}
          </div>
        </Can>
      </div>

      {/* Печать бланка наряда */}
      <PrintButtons onDownload={(fmt) => void handleDownload(fmt)} />

      {/* Main content grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Left: permit details */}
        <div className="rounded-md border p-3 space-y-3">
          <div className="text-sm font-medium">Сведения о работах</div>
          <Section title="Содержание работ" value={wp.content_text} />
          <Section title="Условия проведения" value={wp.conditions_text} />
          <Section title="Опасные факторы" value={wp.hazards_text} />
          {wp.work_type === "height" ? (
            <Section title="Системы безопасности" value={safetySystemsText} />
          ) : null}
          <Section title="Мероприятия до начала" value={wp.measures_before_text} />
          <Section title="Мероприятия в процессе" value={wp.measures_during_text} />
          <Section title="Особые условия" value={wp.special_conditions_text} />
          <Section title="СИЗ" value={wp.ppe_text} />
          {wp.work_type === "confined_space" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Анализ воздушной среды и вентиляция (902н)</div>
              {(wp.type_specific as { ventilation?: string }).ventilation ? (
                <div>Вентиляция: {VENTILATION_LABELS[(wp.type_specific as { ventilation: string }).ventilation] ?? "—"}</div>
              ) : null}
              {((wp.type_specific as { gas_analysis?: Array<{ parameter: string; value: string }> }).gas_analysis ?? []).map((m, i) => (
                <div key={i}>{GAS_PARAMETER_LABELS[m.parameter] ?? m.parameter}: {m.value}</div>
              ))}
            </div>
          ) : null}
          {wp.work_type === "hot_work" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Пожарная безопасность огневых работ (1479)</div>
              {((wp.type_specific as { fire_fighting_means?: string[] }).fire_fighting_means ?? []).length ? (
                <div>
                  Средства пожаротушения:{" "}
                  {((wp.type_specific as { fire_fighting_means: string[] }).fire_fighting_means)
                    .map((c) => FIRE_FIGHTING_MEANS_LABELS[c] ?? c)
                    .join(", ")}
                </div>
              ) : null}
              {((wp.type_specific as { gas_analysis?: Array<{ parameter: string; value: string }> }).gas_analysis ?? []).map((m, i) => (
                <div key={i}>{GAS_PARAMETER_LABELS[m.parameter] ?? m.parameter}: {m.value}</div>
              ))}
            </div>
          ) : null}
          {wp.work_type === "gas_hazardous" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Защита органов дыхания и анализ среды (528)</div>
              {((wp.type_specific as { respiratory_ppe?: string[] }).respiratory_ppe ?? []).length ? (
                <div>
                  СИЗОД:{" "}
                  {((wp.type_specific as { respiratory_ppe: string[] }).respiratory_ppe)
                    .map((c) => RESPIRATORY_PPE_LABELS[c] ?? c)
                    .join(", ")}
                </div>
              ) : null}
              {((wp.type_specific as { gas_analysis?: Array<{ parameter: string; value: string }> }).gas_analysis ?? []).map((m, i) => (
                <div key={i}>{GAS_PARAMETER_LABELS[m.parameter] ?? m.parameter}: {m.value}</div>
              ))}
            </div>
          ) : null}
          {wp.work_type === "electrical" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Меры безопасности в электроустановках (903н)</div>
              {(wp.type_specific as { voltage_condition?: string }).voltage_condition ? (
                <div>
                  Условие проведения:{" "}
                  {VOLTAGE_CONDITION_LABELS[
                    (wp.type_specific as { voltage_condition: string }).voltage_condition
                  ] ?? "—"}
                </div>
              ) : null}
              {((wp.type_specific as { technical_measures?: string[] }).technical_measures ?? []).length ? (
                <div>
                  Технические мероприятия:{" "}
                  {((wp.type_specific as { technical_measures: string[] }).technical_measures)
                    .map((c) => ELECTRICAL_MEASURES_LABELS[c] ?? c)
                    .join("; ")}
                </div>
              ) : null}
            </div>
          ) : null}
          {!wp.content_text &&
            !wp.conditions_text &&
            !wp.hazards_text &&
            !wp.safety_systems?.length &&
            !wp.measures_before_text &&
            !wp.measures_during_text &&
            !wp.special_conditions_text &&
            !wp.ppe_text && (
              <p className="text-sm text-muted-foreground">Описательные поля не заполнены</p>
            )}
        </div>

        {/* Right: brigade + readiness */}
        <div className="space-y-4">
          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Бригада</div>
            <BrigadeMembersPanel
              wp={wp}
              persons={persons}
              nameOf={nameOf}
              onRefresh={() => void reload()}
            />
          </div>
          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Готовность бригады</div>
            <ReadinessPanel report={readiness} nameOf={nameOf} />
          </div>
        </div>
      </div>

      {/* Dates strip */}
      <div className="flex flex-wrap gap-4 text-sm">
        {wp.planned_start && (
          <span>
            <span className="text-muted-foreground">Начало: </span>
            {new Date(wp.planned_start).toLocaleString("ru-RU")}
          </span>
        )}
        {wp.planned_end && (
          <span>
            <span className="text-muted-foreground">Окончание: </span>
            {new Date(wp.planned_end).toLocaleString("ru-RU")}
          </span>
        )}
        {wp.opened_at && (
          <span>
            <span className="text-muted-foreground">Выдан: </span>
            {new Date(wp.opened_at).toLocaleString("ru-RU")}
          </span>
        )}
        {wp.closed_at && (
          <span>
            <span className="text-muted-foreground">Закрыт: </span>
            {new Date(wp.closed_at).toLocaleString("ru-RU")}
          </span>
        )}
        {wp.suspended_at && (
          <span>
            <span className="text-muted-foreground">Приостановлен: </span>
            {new Date(wp.suspended_at).toLocaleString("ru-RU")}
          </span>
        )}
      </div>

      {/* Целевой инструктаж */}
      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Целевой инструктаж</div>
        <BriefingPanel wp={wp} nameOf={nameOf} signatures={signatures} onRefresh={refreshSide} />
      </div>

      {/* Подписи ответственных лиц */}
      <div className="rounded-md border p-3">
        <SignaturesPanel
          title="Подписи ответственных"
          signers={responsibleSigners}
          signatures={permitSignatures}
          onSign={signPermit}
          onConfirm={confirmSign}
        />
      </div>

      {/* Ежедневный допуск */}
      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Ежедневный допуск</div>
        <DailyAdmissionPanel wp={wp} onRefresh={refreshSide} />
      </div>

      {/* Закрытие наряда (Ф3b) — только для issued / suspended / closed */}
      {["issued", "suspended", "closed"].includes(wp.status) && closingSummary && (
        <div className="rounded-md border p-3">
          <div className="text-sm font-medium mb-2">Закрытие наряда</div>
          <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
            {(canManage) => (
              <ClosingPanel
                summary={closingSummary}
                signers={closingSigners}
                canManage={canManage}
                workPermitId={wp.id}
                nameOf={nameOf}
                onRefresh={refreshSide}
                onClose={() => void runAction("close")}
              />
            )}
          </Can>
        </div>
      )}

      {/* Events log */}
      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Журнал событий</div>
        <WorkPermitEventsTimeline events={events} nameOf={nameOf} />
      </div>
    </div>
  );
}
