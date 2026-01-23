import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

export const DocumentPreview = ({ document }: { document: DocumentDto }) => {
  const { refreshStatus, download } = useDocumentsStore();
  const [current, setCurrent] = useState(document);

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
          <Button variant="outline" onClick={handleRefresh}>
            Обновить статус
          </Button>
          <Button onClick={handleDownload}>Скачать</Button>
        </div>
      </CardHeader>
      <CardContent>
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
