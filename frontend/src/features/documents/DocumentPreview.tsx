import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ActionButton } from "@/components/permissions/ActionButton";
import { releaseApi, type ReleaseStatus } from "@/api/release";
import { approvalsApi } from "@/api/approvals";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

interface DocumentPreviewProps {
  document: DocumentDto;
  initialTab?: "preview" | "history" | "timeline";
}

export const DocumentPreview = ({ document, initialTab = "preview" }: DocumentPreviewProps) => {
  const { refreshStatus, download } = useDocumentsStore();
  const [current, setCurrent] = useState(document);
  const [release, setRelease] = useState<ReleaseStatus>({ approval: "draft", signature: "pending", edo: "queued" });
  const [myTaskId, setMyTaskId] = useState<string | null>(null);
  const { can } = useAbility();
  const resource = {
    status: current.status,
    company_id: current.company?.id
  };

  useEffect(() => {
    setCurrent(document);
    releaseApi.documentReleaseStatus(document.id).then(setRelease).catch(() => undefined);
    approvalsApi.listMyTasks("pending").then((items) => {
      const mine = items.find((it) => (it.instance_id || it.process_id));
      setMyTaskId(mine?.id ?? null);
    }).catch(() => undefined);
  }, [document]);

  const handleRefresh = async () => {
    const updated = await refreshStatus(document.id);
    if (updated) {
      setCurrent(updated);
      toast.success("Статус обновлён");
    }
  };

  const handleDownload = async () => {
    const blob = await download(document.id);
    downloadBlob(blob, `${document.name}.pdf`);
  };


  const handleQuickApprove = async () => {
    if (!myTaskId) return;
    await releaseApi.quickApprove(myTaskId, "mobile approve");
    toast.success("Согласовано");
    releaseApi.documentReleaseStatus(document.id).then(setRelease).catch(() => undefined);
  };

  const handleQuickReject = async () => {
    if (!myTaskId) return;
    await releaseApi.quickReject(myTaskId, "mobile reject");
    toast.success("Отклонено");
    releaseApi.documentReleaseStatus(document.id).then(setRelease).catch(() => undefined);
  };

  const handleQuickSign = async () => {
    await releaseApi.quickSign(document.id);
    toast.success("Подпись отправлена");
    releaseApi.documentReleaseStatus(document.id).then(setRelease).catch(() => undefined);
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
        <div className="mb-4 grid gap-2 rounded-md border p-3 text-sm sm:grid-cols-3">
          <div><span className="text-muted-foreground">Approval:</span> <Badge variant="secondary">{release.approval}</Badge></div>
          <div><span className="text-muted-foreground">Signature:</span> <Badge variant="secondary">{release.signature}</Badge></div>
          <div><span className="text-muted-foreground">EDO:</span> <Badge variant="secondary">{release.edo}</Badge></div>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} variant="outline" onClick={handleQuickApprove}>Согласовать</ActionButton>
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} variant="outline" onClick={handleQuickReject}>Отклонить</ActionButton>
          <ActionButton permission={PERMISSIONS.DOCUMENT_SIGN} abilityResource={resource} onClick={handleQuickSign}>Подписать</ActionButton>
        </div>
        {!can(PERMISSIONS.DOCUMENT_SIGN, resource) && (
          <div className="mb-3 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Режим только для чтения
          </div>
        )}
        <Tabs defaultValue={initialTab} className="space-y-4">
          <TabsList>
            <TabsTrigger value="preview">Предпросмотр</TabsTrigger>
            <TabsTrigger value="history">История</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
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
