import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ActionButton } from "@/components/permissions/ActionButton";
import { getDocumentReadiness } from "@/api/documents";
import { releaseApi, type ReleaseStatus } from "@/api/release";
import { approvalsApi } from "@/api/approvals";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto, DocumentReadinessDto } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

interface DocumentPreviewProps {
  document: DocumentDto;
  initialTab?: "preview" | "history" | "timeline";
}

type PreviewTab = NonNullable<DocumentPreviewProps["initialTab"]>;

export const DocumentPreview = ({ document, initialTab = "preview" }: DocumentPreviewProps) => {
  const { refreshStatus, download } = useDocumentsStore();
  const [current, setCurrent] = useState(document);
  const [activeTab, setActiveTab] = useState<PreviewTab>(initialTab);
  const [release, setRelease] = useState<ReleaseStatus>({ approval: "draft", signature: "pending", edo: "queued" });
  const [readiness, setReadiness] = useState<DocumentReadinessDto | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [myTaskId, setMyTaskId] = useState<string | null>(null);
  const { can } = useAbility();
  const releaseTargetId = current.current_version_id ?? current.id;
  const resource = {
    status: current.status,
    company_id: current.company?.id
  };

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    setCurrent(document);
    releaseApi.documentReleaseStatus(document.current_version_id ?? document.id).then(setRelease).catch(() => undefined);
    approvalsApi.listMyTasks("pending").then((items) => {
      const mine = items.find((it) => (it.instance_id || it.process_id));
      setMyTaskId(mine?.id ?? null);
    }).catch(() => undefined);
    setReadinessLoading(true);
    getDocumentReadiness(document.id)
      .then(setReadiness)
      .catch(() => setReadiness(null))
      .finally(() => setReadinessLoading(false));
  }, [document]);

  const handleRefresh = async () => {
    const updated = await refreshStatus(document.id);
    if (updated) {
      setCurrent(updated);
      toast.success("Статус обновлён");
    }
    setReadinessLoading(true);
    try {
      const next = await getDocumentReadiness(document.id);
      setReadiness(next);
    } catch {
      setReadiness(null);
    } finally {
      setReadinessLoading(false);
    }
  };

  const handleDownload = async () => {
    const blob = await download(document.id);
    downloadBlob(blob, `${document.name}.pdf`);
  };


  const handleQuickApprove = async () => {
    if (!myTaskId) return;
    try {
      await releaseApi.quickApprove(myTaskId, "mobile approve");
      toast.success("Согласовано");
      releaseApi.documentReleaseStatus(releaseTargetId).then(setRelease).catch(() => undefined);
    } catch {
      toast.error("Не удалось согласовать");
    }
  };

  const handleQuickReject = async () => {
    if (!myTaskId) return;
    try {
      await releaseApi.quickReject(myTaskId, "mobile reject");
      toast.success("Отклонено");
      releaseApi.documentReleaseStatus(releaseTargetId).then(setRelease).catch(() => undefined);
    } catch {
      toast.error("Не удалось отклонить");
    }
  };

  const handleQuickSign = async () => {
    try {
      await releaseApi.quickSign(releaseTargetId);
      toast.success("Подпись отправлена");
      releaseApi.documentReleaseStatus(releaseTargetId).then(setRelease).catch(() => undefined);
    } catch {
      toast.error("Не удалось отправить подпись");
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="text-xl font-semibold">{current.name}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {current.type} • Версия {current.version} • {formatDate(current.updated_at)}
          </p>
        </div>
        <div className="flex gap-2">
          <ActionButton
            permission={PERMISSIONS.DOCUMENT_SIGN}
            abilityResource={resource}
            variant="outline"
            disabledReason="Подписание возможно после готовности документа"
            onClick={handleRefresh}
          >
            Обновить статус
          </ActionButton>
          <ActionButton
            permission={PERMISSIONS.DOCUMENT_EXPORT}
            abilityResource={resource}
            disabledReason="Экспорт доступен после готовности документа"
            onClick={handleDownload}
          >
            Скачать
          </ActionButton>
        </div>
      </CardHeader>
      <CardContent>
        <div
          className="mb-4 rounded-md border bg-muted/30 p-4"
          data-testid="document-readiness-panel"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Готовность к выпуску (readiness)</div>
            {readinessLoading ? (
              <span className="text-xs text-muted-foreground">Расчёт…</span>
            ) : readiness ? (
              <Badge variant={readiness.score >= 80 ? "default" : readiness.score >= 50 ? "secondary" : "destructive"}>
                {readiness.score}%
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">Нет данных</span>
            )}
          </div>
          {readiness && !readinessLoading ? (
            <div className="mt-3 space-y-3 text-sm">
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-[width]"
                  style={{ width: `${Math.min(100, Math.max(0, readiness.score))}%` }}
                />
              </div>
              {(readiness.blockers?.length ?? 0) > 0 ? (
                <div>
                  <p className="mb-1 text-xs font-medium text-destructive">Препятствия</p>
                  <ul className="list-inside list-disc text-xs text-muted-foreground">
                    {(readiness.blockers ?? []).map((b, i) => (
                      <li key={`blocker-${i}-${b.slice(0, 24)}`}>{b}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {(readiness.recommended_actions?.length ?? 0) > 0 ? (
                <div>
                  <p className="mb-1 text-xs font-medium text-foreground">Рекомендуемые действия</p>
                  <ul className="list-inside list-disc text-xs text-muted-foreground">
                    {(readiness.recommended_actions ?? []).map((a, i) => (
                      <li key={`action-${i}-${a.slice(0, 24)}`}>{a}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {readiness.pipeline_stages && readiness.pipeline_stages.length > 0 ? (
                <div data-testid="document-pipeline-stages">
                  <p className="mb-1 text-xs font-medium text-foreground">Контур выпуска</p>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    {readiness.pipeline_stages.map((s) => (
                      <li key={s.stage_id} className="flex gap-2">
                        <span className={s.complete ? "text-emerald-600" : "text-amber-600"}>
                          {s.complete ? "✓" : "○"}
                        </span>
                        <span>
                          {s.label}
                          {s.detail ? (
                            <span className="block text-[11px] text-muted-foreground/90">{s.detail}</span>
                          ) : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="mb-4 grid gap-2 rounded-md border p-3 text-sm sm:grid-cols-3">
          <div><span className="text-muted-foreground">Approval:</span> <Badge variant="secondary">{release.approval}</Badge></div>
          <div><span className="text-muted-foreground">Signature:</span> <Badge variant="secondary">{release.signature}</Badge></div>
          <div><span className="text-muted-foreground">EDO:</span> <Badge variant="secondary">{release.edo}</Badge></div>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} variant="outline" disabled={!myTaskId} title={myTaskId ? undefined : "Нет назначенной вам задачи согласования"} onClick={handleQuickApprove}>Согласовать</ActionButton>
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} variant="outline" disabled={!myTaskId} title={myTaskId ? undefined : "Нет назначенной вам задачи согласования"} onClick={handleQuickReject}>Отклонить</ActionButton>
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} onClick={handleQuickSign}>Подписать</ActionButton>
        </div>
        {!can(PERMISSIONS.DOCUMENT_SIGN, resource) && (
          <div className="mb-3 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Режим только для чтения
          </div>
        )}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as PreviewTab)} className="space-y-4">
          <TabsList>
            <TabsTrigger value="preview">Предпросмотр</TabsTrigger>
            <TabsTrigger value="history">История</TabsTrigger>
            <TabsTrigger value="timeline">Хронология</TabsTrigger>
          </TabsList>
          <TabsContent value="preview" className="space-y-3">
            {current.storage?.url ? (
              <iframe
                title={`Предпросмотр ${current.name}`}
                src={current.storage.url}
                className="h-[600px] w-full rounded-md border"
              />
            ) : (
              <p className="text-sm text-muted-foreground">Файл недоступен.</p>
            )}
          </TabsContent>
          <TabsContent value="history" className="space-y-2">
            {current.history?.length ? (
              current.history.map((version) => (
                <div key={version.id} className="rounded-md border p-3 text-sm">
                  <div className="font-medium">Версия {version.id}</div>
                  <div className="text-xs text-muted-foreground">
                    {formatDate(version.created_at)} • {version.status}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">История отсутствует.</p>
            )}
          </TabsContent>
          <TabsContent value="timeline" className="space-y-3">
            {[
              { label: "Согласование", value: release.approval },
              { label: "Подписание", value: release.signature },
              { label: "ЭДО", value: release.edo }
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-md border p-3 text-sm">
                <span className="text-muted-foreground">{item.label}</span>
                <Badge>{item.value}</Badge>
              </div>
            ))}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};
