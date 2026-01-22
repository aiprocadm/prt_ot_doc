import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { DocumentPreview } from "@/features/documents/DocumentPreview";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";

const DocumentsPage = () => {
  const { list } = useDocumentsStore();
  const [selectedDocument, setSelectedDocument] = useState<DocumentDto | null>(null);

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Документы" }]} />
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
