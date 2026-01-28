import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ActionButton } from "@/components/permissions/ActionButton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

export const DocumentPreview = ({ document }: { document: DocumentDto }) => {
  const { refreshStatus, download } = useDocumentsStore();
  const [current, setCurrent] = useState(document);
  const { can } = useAbility();
  const resource = {
    status: current.status,
    company_id: current.company?.id
  };

  useEffect(() => {
    setCurrent(document);
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
            resource={resource}
            variant="outline"
            disabledReason="Подписание возможно после готовности документа"
            onClick={handleRefresh}
          >
            Обновить статус
          </ActionButton>
          <ActionButton
            permission={PERMISSIONS.DOCUMENT_EXPORT}
            resource={resource}
            disabledReason="Экспорт доступен после готовности документа"
            onClick={handleDownload}
          >
            Скачать
          </ActionButton>
        </div>
      </CardHeader>
      <CardContent>
        {!can(PERMISSIONS.DOCUMENT_SIGN, resource) && (
          <div className="mb-3 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Режим только для чтения
          </div>
        )}
        <Tabs defaultValue="preview" className="space-y-4">
          <TabsList>
            <TabsTrigger value="preview">Предпросмотр</TabsTrigger>
            <TabsTrigger value="history">История</TabsTrigger>
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
        </Tabs>
      </CardContent>
    </Card>
  );
};
