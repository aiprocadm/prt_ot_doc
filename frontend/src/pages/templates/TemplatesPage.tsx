import { useEffect, useState } from "react";

import { ListStateGuard } from "@/components/common/ListStateGuard";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TemplateDetails } from "@/features/templates/TemplateDetails";
import { TemplateFormDialog } from "@/features/templates/TemplateFormDialog";
import { TemplateTable } from "@/features/templates/TemplateTable";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { ROUTES } from "@/router/routes";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";

const TemplatesPage = () => {
  const { list, getById, items, loading, error } = useTemplatesStore();
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDto | null>(
    null,
  );
  const { can } = useAbility();
  const canView = can(PERMISSIONS.TEMPLATE_VIEW);
  const canCreate = can(PERMISSIONS.TEMPLATE_CREATE);
  const canEdit = can(PERMISSIONS.TEMPLATE_EDIT);
  const readOnly = !canCreate && !canEdit;

  useEffect(() => {
    if (canView) {
      list();
    }
  }, [canView, list]);

  if (!canView) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb
          items={[
            { label: "Главная", to: ROUTES.DASHBOARD },
            { label: "Шаблоны" },
          ]}
        />
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Шаблоны</h1>
          <div className="flex items-center gap-2">
            {readOnly && (
              <span className="rounded-full border border-dashed px-3 py-1 text-xs text-muted-foreground">
                Только просмотр
              </span>
            )}
            {canCreate && (
              <TemplateFormDialog
                trigger={<Button>Добавить</Button>}
                onSubmitted={(template) => {
                  setSelectedTemplate(template);
                  list();
                }}
              />
            )}
          </div>
        </div>
      </div>
      <Card>
        <CardContent className="py-6">
          <ListStateGuard
            error={error}
            loading={loading}
            itemsCount={items.length}
            loadingLabel="Загрузка шаблонов"
            emptyTitle="Шаблоны не найдены"
            emptyDescription="Загрузите первый шаблон, чтобы запустить жизненный цикл документов без ручных обходных сценариев."
            onRetry={() => void list()}
          >
            <TemplateTable
              onSelect={(template) => {
                getById(template.id).then((loaded) =>
                  setSelectedTemplate(loaded ?? template),
                );
              }}
            />
          </ListStateGuard>
        </CardContent>
      </Card>
      {selectedTemplate && <TemplateDetails template={selectedTemplate} />}
    </div>
  );
};

export default TemplatesPage;
