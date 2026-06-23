import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import {
  generateDocument,
  getGenerationTaskStatus,
  resolveTemplateForQuickGenerate,
  type TaskStatusResponse,
  type TemplateResolveResponse,
} from "@/api/documents";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePolling } from "@/hooks/usePolling";
import { useDocumentsWizardBootstrap } from "@/pages/documents/wizard/useDocumentsWizardBootstrap";
import { PERMISSIONS } from "@/permissions/permissions";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { useAbility } from "@/permissions/useAbility";
import { usePersonsStore } from "@/stores/persons";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";
import { trackUxMetric } from "@/utils/uxMetrics";
import type { PersonDto } from "@/types/dto/persons";

const createIdempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const isTerminalStatus = (status: string | undefined) =>
  Boolean(status && ["success", "failed", "done", "error", "canceled"].includes(status));

const ORCHESTRATION_LABELS: Record<string, string> = {
  generated: "Документ сгенерирован",
  headers_applied: "Колонтитулы применены",
  pdf_ready: "PDF подготовлен",
  handoff_ready: "Готов к передаче дальше",
  retrying: "Повторная попытка",
  failed: "Ошибка",
};

const STEP_ORDER = ["generated", "headers_applied", "pdf_ready", "handoff_ready", "retrying", "failed"];

const getUserFacingError = (task: TaskStatusResponse | null) => {
  const value = task?.metadata && typeof task.metadata === "object"
    ? (task.metadata["user_facing_error"] as string | undefined)
    : undefined;
  return value ?? task?.error ?? null;
};

const QuickGeneratePage = () => {
  const { can } = useAbility();
  const [searchParams] = useSearchParams();
  const canCreate = can(PERMISSIONS.DOCUMENT_CREATE);
  const { tenant, companies, sites } = useDocumentsWizardBootstrap();
  const { items: persons, list: listPersons, setPageSize } = usePersonsStore();
  const { quickGenerationHistory, pushQuickGenerationHistory } = useDocumentsWizardStore();

  const [companyId, setCompanyId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [personId, setPersonId] = useState("");
  const [caseType, setCaseType] = useState("employment");
  const [documentType, setDocumentType] = useState("order");
  const [category, setCategory] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [comments, setComments] = useState("");
  const [resolving, setResolving] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [resolved, setResolved] = useState<TemplateResolveResponse | null>(null);
  const [task, setTask] = useState<TaskStatusResponse | null>(null);
  const [pollingInterval, setPollingInterval] = useState(2000);

  useEffect(() => {
    const prefillCompanyId = searchParams.get("company_id");
    const prefillPersonId = searchParams.get("person_id");
    if (prefillCompanyId) {
      setCompanyId(prefillCompanyId);
    }
    if (prefillPersonId) {
      setPersonId(prefillPersonId);
    }
  }, [searchParams]);

  useEffect(() => {
    setPageSize(200);
    void listPersons().catch(() => undefined);
  }, [listPersons, setPageSize]);

  useEffect(() => {
    if (!companyId && companies.length > 0) {
      setCompanyId(companies[0].id);
    }
  }, [companies, companyId]);

  // Подобранный шаблон привязан к конкретным компании/площадке/сотруднику/типу случая.
  // При изменении любого входа сбрасываем подбор — иначе «Сгенерировать» уйдёт со старым
  // template_code под новые данные (шаблон молча не соответствует выбору пользователя).
  useEffect(() => {
    setResolved(null);
  }, [companyId, siteId, personId, caseType, documentType, category]);

  const selectedPerson = useMemo<PersonDto | undefined>(
    () => persons.find((item) => item.id === personId),
    [persons, personId]
  );

  const runResolve = async () => {
    if (!tenant) return;
    if (!companyId) {
      toast.error("Выберите компанию.");
      return;
    }
    setResolving(true);
    try {
      const next = await resolveTemplateForQuickGenerate({
        case_type: caseType,
        document_type: documentType,
        category: category || undefined,
        company_id: companyId,
        site_id: siteId || undefined,
        person_id: personId || undefined,
      });
      setResolved(next);
      trackUxMetric("navigation_click", { source: "quick-generate-resolve", scope: next.scope_level });
      toast.success(`Шаблон подобран: ${next.template_name} v${next.template_version}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось подобрать шаблон");
      setResolved(null);
    } finally {
      setResolving(false);
    }
  };

  const runGenerate = async () => {
    if (!resolved) {
      toast.error("Сначала выполните подбор шаблона.");
      return;
    }
    if (!companyId) {
      toast.error("Выберите компанию.");
      return;
    }
    setLaunching(true);
    try {
      const idempotencyKey = createIdempotencyKey();
      const startedAt = Date.now();
      const accepted = await generateDocument(
        {
          template_code: resolved.template_code,
          template_version: resolved.template_version,
          company_id: companyId,
          person_id: personId || undefined,
          data: {
            case_type: caseType,
            document_type: documentType,
            category: category || null,
            effective_date: effectiveDate || null,
            comments: comments || null,
            person: selectedPerson
              ? {
                  id: selectedPerson.id,
                  full_name: [selectedPerson.last_name, selectedPerson.first_name, selectedPerson.middle_name]
                    .filter(Boolean)
                    .join(" "),
                  position: selectedPerson.position ?? null,
                }
              : null,
            siteId: siteId || null,
            quick_generate: true,
          },
        },
        idempotencyKey
      );
      const initialTask = await getGenerationTaskStatus(accepted.task_id);
      setTask(initialTask);
      setPollingInterval(2000);
      pushQuickGenerationHistory({
        id: accepted.task_id,
        createdAt: new Date().toISOString(),
        personId,
        companyId,
        siteId,
        caseType,
        templateCode: resolved.template_code,
        templateVersion: resolved.template_version,
        taskId: accepted.task_id,
        status: initialTask.status,
      });
      trackUxMetric("time_to_first_action", {
        source: "quick-generate",
        accepted_ms: Date.now() - startedAt,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось запустить генерацию");
    } finally {
      setLaunching(false);
    }
  };

  usePolling(
    async () => {
      if (!task?.task_id || isTerminalStatus(task.status)) return;
      const next = await getGenerationTaskStatus(task.task_id);
      setTask(next);
      setPollingInterval((prev) => (isTerminalStatus(next.status) ? 2000 : Math.min(prev + 1000, 8000)));
      if (next.status === "success" || next.status === "done") {
        toast.success("Документ готов.");
      }
      if (next.status === "failed" || next.status === "error") {
        toast.error(next.error ?? "Генерация завершилась с ошибкой");
      }
    },
    pollingInterval,
    {
      enabled: Boolean(task?.task_id) && !isTerminalStatus(task?.status),
      onError: () => {
        setPollingInterval((prev) => Math.min(prev + 2000, 12000));
      },
    }
  );

  const orchestration = task?.metadata && typeof task.metadata === "object"
    ? ((task.metadata["orchestration"] as Record<string, unknown> | undefined) ?? undefined)
    : undefined;
  const orchestrationState = typeof orchestration?.state === "string" ? orchestration.state : null;
  const timelineStates = Array.isArray(orchestration?.timeline)
    ? (orchestration.timeline as Array<Record<string, unknown>>).map((item) => String(item.state ?? ""))
    : [];

  if (!canCreate) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Документы", to: "/documents" },
          { label: "Быстрая генерация" },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>Быстрая генерация для сотрудника/случая</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="qg-company">Компания</Label>
              <select
                id="qg-company"
                className="h-10 w-full rounded-md border px-3"
                value={companyId}
                onChange={(event) => setCompanyId(event.target.value)}
              >
                <option value="">— Выберите компанию —</option>
                {companies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-site">Филиал/площадка</Label>
              <select
                id="qg-site"
                className="h-10 w-full rounded-md border px-3"
                value={siteId}
                onChange={(event) => setSiteId(event.target.value)}
              >
                <option value="">— Без филиала —</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-person">Сотрудник</Label>
              <select
                id="qg-person"
                className="h-10 w-full rounded-md border px-3"
                value={personId}
                onChange={(event) => setPersonId(event.target.value)}
              >
                <option value="">— Не выбран —</option>
                {persons.map((person) => (
                  <option key={person.id} value={person.id}>
                    {[person.last_name, person.first_name, person.middle_name].filter(Boolean).join(" ")}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-case">Тип случая</Label>
              <Input id="qg-case" value={caseType} onChange={(event) => setCaseType(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-doc-type">Тип документа</Label>
              <Input id="qg-doc-type" value={documentType} onChange={(event) => setDocumentType(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-category">Категория (опционально)</Label>
              <Input id="qg-category" value={category} onChange={(event) => setCategory(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-date">Дата действия</Label>
              <Input id="qg-date" type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qg-comments">Комментарий</Label>
              <Input id="qg-comments" value={comments} onChange={(event) => setComments(event.target.value)} />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => void runResolve()} disabled={resolving || launching}>
              {resolving ? "Подбираем шаблон..." : "Подобрать шаблон"}
            </Button>
            <Button onClick={() => void runGenerate()} disabled={!resolved || launching}>
              {launching ? "Запуск..." : "Сгенерировать"}
            </Button>
            <Button asChild variant="ghost">
              <Link to="/documents/wizard">Открыть расширенный мастер</Link>
            </Button>
          </div>

          {resolved ? (
            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">
                Выбран шаблон: {resolved.template_name} ({resolved.template_code}) v{resolved.template_version}
              </p>
              <p className="text-muted-foreground">Приоритет: {resolved.scope_level}. Цепочка: {resolved.resolution_chain.join(" -> ")}.</p>
            </div>
          ) : null}

          {task ? (
            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">Статус запуска: {task.status}</p>
              {getUserFacingError(task) ? <p className="text-destructive">{getUserFacingError(task)}</p> : null}
              {task.document_id ? <p>Документ: {task.document_id}</p> : null}
              {task.document_version_id ? <p>Версия: {task.document_version_id}</p> : null}
              <div className="mt-3 grid gap-1">
                <p className="text-xs text-muted-foreground">Этапы оркестрации:</p>
                {STEP_ORDER.map((step) => {
                  const isDone = timelineStates.includes(step);
                  const isCurrent = orchestrationState === step;
                  return (
                    <div key={step} className="flex items-center gap-2 text-xs">
                      <span>{isDone ? "✅" : isCurrent ? "🟡" : "⚪"}</span>
                      <span className={step === "failed" && isDone ? "text-destructive" : ""}>{ORCHESTRATION_LABELS[step] ?? step}</span>
                    </div>
                  );
                })}
              </div>
              {(task.status === "failed" || task.status === "error") ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {personId ? (
                    <Button asChild size="sm" variant="outline">
                      <Link to={`/persons?person_id=${encodeURIComponent(personId)}`}>Исправить данные сотрудника</Link>
                    </Button>
                  ) : null}
                  <Button size="sm" variant="outline" onClick={() => setResolved(null)}>
                    Сменить шаблон
                  </Button>
                  <Button size="sm" onClick={() => void runGenerate()}>
                    Повторить с новым ключом
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Последние быстрые запуски</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {quickGenerationHistory.length === 0 ? (
            <p className="text-muted-foreground">История пока пуста.</p>
          ) : (
            quickGenerationHistory.map((item) => (
              <div key={item.id} className="rounded-md border p-2">
                <p className="font-medium">
                  {item.templateCode} v{item.templateVersion} · {item.caseType}
                </p>
                <p className="text-muted-foreground">
                  task: {item.taskId} · person: {item.personId || "—"} · status: {item.status}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default QuickGeneratePage;
