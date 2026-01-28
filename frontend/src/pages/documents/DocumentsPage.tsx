import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { DocumentPreview } from "@/features/documents/DocumentPreview";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";

const DocumentsPage = () => {
  const { list } = useDocumentsStore();
  const [selectedDocument, setSelectedDocument] = useState<DocumentDto | null>(null);
  const { can } = useAbility();
  const canView = can(PERMISSIONS.DOCUMENT_VIEW);

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
