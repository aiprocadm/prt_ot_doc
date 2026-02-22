import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { ActionButton } from "@/components/permissions/ActionButton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PERMISSIONS } from "@/permissions/permissions";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";
import { formatDate } from "@/utils/datetime";

export const TemplateDetails = ({ template }: { template: TemplateDto }) => {
  const { activateVersion } = useTemplatesStore();
  const [isActivating, setIsActivating] = useState(false);

  const handleActivate = async (versionId: string) => {
    setIsActivating(true);
    try {
      await activateVersion(template.id, versionId);
      toast.success("Версия активирована");
    } finally {
      setIsActivating(false);
    }
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
          <TabsContent value="meta" className="grid gap-2 text-sm">
            <div>Создано: {formatDate(template.created_at)}</div>
            <div>Обновлено: {formatDate(template.updated_at)}</div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};
