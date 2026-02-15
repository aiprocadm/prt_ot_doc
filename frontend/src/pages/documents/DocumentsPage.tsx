import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { DocumentPreview } from "@/features/documents/DocumentPreview";
import { DocumentCreateWizard } from "@/features/documents/DocumentCreateWizard";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { PermissionGate } from "@/components/permissions/PermissionGate";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";

const DocumentsPage = () => {
  const { list, items, pagination, loading } = useDocumentsStore();
  const [selectedDocument, setSelectedDocument] = useState<DocumentDto | null>(null);
  const { can } = useAbility();
  const canView = can(PERMISSIONS.DOCUMENT_VIEW);

  const statusCounts = items.reduce(
    (acc, document) => {
      acc[document.status] = (acc[document.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<DocumentDto["status"], number>
  );

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
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Документы" }]} />
      <RegistryPageHeader
        title="Документы"
        description="Все корпоративные документы, шаблоны и версии с контролем статуса и компании."
        actions={
          <span className="text-sm text-muted-foreground">
            {loading ? "Обновление списка…" : "Данные актуальны"}
          </span>
        }
        stats={[
          { label: "Всего документов", value: pagination.total },
          { label: "Готовые (на странице)", value: statusCounts.ready ?? 0 },
          { label: "Черновики (на странице)", value: statusCounts.draft ?? 0 },
          { label: "Ошибки (на странице)", value: statusCounts.error ?? 0 }
        ]}
      />
      <PermissionGate permission={PERMISSIONS.DOCUMENT_CREATE}>
        <DocumentCreateWizard />
      </PermissionGate>
      <Card>
        <CardContent className="py-6">
          <DocumentTable onSelect={setSelectedDocument} />
        </CardContent>
      </Card>
      {selectedDocument && <DocumentPreview document={selectedDocument} />}
    </div>
  );
};

export default DocumentsPage;
