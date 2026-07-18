import { AlertCircle, CheckCircle2, Loader2, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCompaniesStore } from "@/stores/companies";
import { useDocumentsStore } from "@/stores/documents";

const createIdempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const normalizePipelineState = (status: string): "queued" | "running" | "done" | "error" => {
  const normalized = String(status).toLowerCase();
  if (normalized === "queued") return "queued";
  if (normalized === "running" || normalized === "processing" || normalized === "pending") return "running";
  if (normalized === "done" || normalized === "success" || normalized === "completed") return "done";
  if (normalized === "error" || normalized === "failed" || normalized === "failure" || normalized === "canceled") return "error";
  return "running";
};

export const DocumentCreateWizard = () => {
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const { generateDocument, getGenerationStatus, list: listDocuments } = useDocumentsStore();
  const safeCompanies = Array.isArray(companies)
    ? companies.filter((company): company is NonNullable<(typeof companies)[number]> => Boolean(company?.id && company?.name))
    : [];

  const [templateCode, setTemplateCode] = useState("");
  const [templateVersion, setTemplateVersion] = useState("1");
  const [companyId, setCompanyId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(createIdempotencyKey());
  const [taskId, setTaskId] = useState<string | null>(null);
  const [pipelineState, setPipelineState] = useState<"idle" | "queued" | "running" | "done" | "error">("idle");
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  useEffect(() => {
    listCompanies().catch(() => undefined);
  }, [listCompanies]);

  useEffect(() => {
    if (!taskId || (pipelineState !== "queued" && pipelineState !== "running")) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await getGenerationStatus(taskId);
        const normalized = normalizePipelineState(status.status);
        setPipelineState(normalized);
        setRequestId(String(status.metadata?.request_id ?? ""));
        if (status.error) {
          setPipelineError(status.error);
        }
        if (normalized === "done") {
          listDocuments().catch(() => undefined);
          toast.success("Документ успешно поставлен в реестр.");
          // Ключ идемпотентности «израсходован» успешной генерацией: ротируем его, иначе
          // повторный «Запустить генерацию» вернёт ту же задачу, и новый документ не создастся.
          setIdempotencyKey(createIdempotencyKey());
          window.clearInterval(timer);
        }
        if (normalized === "error") {
          toast.error("Генерация завершилась ошибкой. Можно повторить с тем же ключом.");
          window.clearInterval(timer);
        }
      } catch {
        setPipelineState("error");
        setPipelineError("Не удалось получить статус генерации. Попробуйте обновить страницу.");
        toast.error("Не удалось обновить статус генерации.");
        window.clearInterval(timer);
      }
    }, 2500);

    return () => window.clearInterval(timer);
  }, [getGenerationStatus, listDocuments, pipelineState, taskId]);

  const canSubmit = useMemo(
    () => Boolean(templateCode.trim()) && Boolean(companyId) && Number(templateVersion) > 0,
    [companyId, templateCode, templateVersion]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Создание документа</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Input placeholder="Код шаблона" value={templateCode} onChange={(event) => setTemplateCode(event.target.value)} />
          <Input
            placeholder="Версия шаблона"
            type="number"
            min={1}
            value={templateVersion}
            onChange={(event) => setTemplateVersion(event.target.value)}
          />
          <select
            aria-label="Компания"
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={companyId}
            onChange={(event) => setCompanyId(event.target.value)}
          >
            <option value="">Выберите компанию</option>
            {safeCompanies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Idempotency-Key: {idempotencyKey}</Badge>
          <Button type="button" variant="outline" size="sm" onClick={() => setIdempotencyKey(createIdempotencyKey())}>
            Сгенерировать новый ключ
          </Button>
          <Button
            type="button"
            disabled={!canSubmit || pipelineState === "queued" || pipelineState === "running"}
            onClick={async () => {
              setPipelineState("queued");
              setPipelineError(null);
              try {
                const task = await generateDocument(
                  {
                    template_code: templateCode.trim(),
                    template_version: Number(templateVersion),
                    company_id: companyId,
                    data: {}
                  },
                  idempotencyKey
                );
                setTaskId(task.task_id);
              } catch (error: unknown) {
                setPipelineState("error");
                const typed = error as { message?: string; details?: { request_id?: string } };
                setPipelineError(typed.message ?? "Не удалось создать задачу генерации.");
                setRequestId(typed.details?.request_id ?? null);
              }
            }}
          >
            Запустить генерацию
          </Button>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {pipelineState === "idle" && <PlayCircle className="h-4 w-4 text-muted-foreground" />}
          {pipelineState === "queued" && <Loader2 className="h-4 w-4 animate-spin" />}
          {pipelineState === "running" && <Loader2 className="h-4 w-4 animate-spin" />}
          {pipelineState === "done" && <CheckCircle2 className="h-4 w-4 text-green-600" />}
          {pipelineState === "error" && <AlertCircle className="h-4 w-4 text-destructive" />}
          <span>
            Pipeline status: <strong>{pipelineState}</strong>
          </span>
          {requestId && <span className="text-muted-foreground">request_id: {requestId}</span>}
        </div>
        {pipelineError && <p className="text-sm text-destructive">{pipelineError}</p>}
      </CardContent>
    </Card>
  );
};
