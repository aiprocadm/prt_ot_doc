import { useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { ActionButton } from "@/components/permissions/ActionButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PERMISSIONS } from "@/permissions/permissions";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";
import { formatDate } from "@/utils/datetime";

export const TemplateDetails = ({ template }: { template: TemplateDto }) => {
  const { activateVersion } = useTemplatesStore();
  const [isActivating, setIsActivating] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [versionId, setVersionId] = useState(template.current_version?.id ?? template.versions?.[0]?.id ?? "");
  const [previewData, setPreviewData] = useState('{"employee": {"name": "Иван"}}');
  const [lintReport, setLintReport] = useState<string>("");

  const handleActivate = async (versionId: string) => {
    setIsActivating(true);
    try {
      await activateVersion(template.id, versionId);
      toast.success("Версия активирована");
    } finally {
      setIsActivating(false);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    await apiClient.post(`/templates/${template.id}/versions:upload`, form, {
      headers: { "Content-Type": "multipart/form-data", "Idempotency-Key": `${template.id}-${file.name}` }
    });
    toast.success("Версия загружена");
  };

  const handleLint = async () => {
    const { data } = await apiClient.post(`/templates/${template.id}/versions/${versionId}:lint`, {
      required_fields: []
    });
    setLintReport(JSON.stringify(data, null, 2));
    toast.success("Lint завершён");
  };

  const handlePreview = async () => {
    const parsed = JSON.parse(previewData);
    const { data } = await apiClient.post(`/templates/${template.id}/versions/${versionId}:preview`, {
      data: parsed,
      render_pdf: false
    });
    toast.success(`Preview готов: ${data.docx_url}`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">{template.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{template.description ?? "Описание отсутствует"}</p>
        <div className="flex flex-wrap gap-2 text-sm">
          {template.category && <Badge variant="secondary">{template.category}</Badge>}
          {template.tags?.map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
        <Tabs defaultValue="versions">
          <TabsList>
            <TabsTrigger value="versions">Версии</TabsTrigger>
            <TabsTrigger value="meta">Метаданные</TabsTrigger>
            <TabsTrigger value="tools">Upload/Lint/Preview</TabsTrigger>
          </TabsList>
          <TabsContent value="versions" className="space-y-2">
            {template.versions?.length ? (
              template.versions.map((version) => (
                <div key={version.id} className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <div className="font-medium">Версия {version.version}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatDate(version.created_at)} • {version.status}
                    </div>
                  </div>
                  <ActionButton
                    permission={PERMISSIONS.TEMPLATE_ACTIVATE}
                    abilityResource={{ template: { current_version: template.current_version }, version }}
                    variant={template.current_version?.id === version.id ? "secondary" : "outline"}
                    size="sm"
                    disabled={template.current_version?.id === version.id || isActivating}
                    disabledReason="Версию можно активировать только если она опубликована и не используется"
                    onClick={() => handleActivate(version.id)}
                  >
                    {template.current_version?.id === version.id ? "Текущая" : "Активировать"}
                  </ActionButton>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Версии не найдены.</p>
            )}
          </TabsContent>
          <TabsContent value="tools" className="space-y-3">
            <Input type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button onClick={handleUpload}>Загрузить версию</Button>
            <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={versionId} onChange={(e) => setVersionId(e.target.value)}>
              <option value="" disabled>Выберите версию шаблона</option>
              {(template.versions ?? []).map((version) => (
                <option key={version.id} value={version.id}>
                  Версия {version.version} · {version.status}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <Button variant="outline" disabled={!versionId} onClick={handleLint}>Lint</Button>
              <Button variant="outline" disabled={!versionId} onClick={handlePreview}>Preview</Button>
            </div>
            <Textarea rows={8} value={previewData} onChange={(e) => setPreviewData(e.target.value)} />
            {lintReport && <pre className="rounded border p-2 text-xs">{lintReport}</pre>}
          </TabsContent>
          <TabsContent value="meta" className="grid gap-2 text-sm">
            <div>Создано: {formatDate(template.created_at)}</div>
            <div>Обновлено: {formatDate(template.updated_at)}</div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};
