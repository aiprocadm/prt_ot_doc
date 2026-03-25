import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { DocumentPreview } from "@/features/documents/DocumentPreview";
import { DocumentCreateWizard } from "@/features/documents/DocumentCreateWizard";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { Button } from "@/components/ui/button";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { PermissionGate } from "@/components/permissions/PermissionGate";
import { useAbility } from "@/permissions/useAbility";
import { useDocumentsStore } from "@/stores/documents";
import type { DocumentDto } from "@/types/dto/documents";
import { entityCardLink } from "@/utils/workspaceNavigation";

const DocumentsPage = () => {
  const { list, items, pagination, loading, error, getById } = useDocumentsStore();
  const [selectedDocument, setSelectedDocument] = useState<DocumentDto | null>(null);
  const [searchParams] = useSearchParams();
  const { can } = useAbility();
  const canView = can(PERMISSIONS.DOCUMENT_VIEW);
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;
  const focusedView = searchParams.get("view") === "timeline" ? "timeline" : "summary";

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

  useEffect(() => {
    if (!canView || !focusedEntityId) return;
    if (!["document", "document_version", "template_version"].includes(focusedEntityType ?? "")) return;

    const existing = items.find((doc) => doc.id === focusedEntityId);
    if (existing) {
      setSelectedDocument(existing);
      return;
    }
    void getById(focusedEntityId).then((doc) => {
      if (doc) setSelectedDocument(doc);
    });
  }, [canView, focusedEntityId, focusedEntityType, getById, items]);

  const focusSummaryLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "summary"),
    [focusedEntityId, focusedEntityType]
  );
  const focusTimelineLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "timeline"),
    [focusedEntityId, focusedEntityType]
  );

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
      {focusedEntityId && ["document", "document_version", "template_version"].includes(focusedEntityType ?? "") ? (
        <Card>
          <CardContent className="py-4" data-testid="document-focus-card">
            <div className="text-sm font-semibold">Фокус документа из рабочего пространства</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {selectedDocument ? `${selectedDocument.name} · ${selectedDocument.status}` : `Документ ${focusedEntityId.slice(0, 8)} загружается...`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {focusSummaryLink ? (
                <Button size="sm" variant={focusedView === "summary" ? "default" : "outline"} asChild>
                  <Link to={focusSummaryLink}>Summary</Link>
                </Button>
              ) : null}
              {focusTimelineLink ? (
                <Button size="sm" variant={focusedView === "timeline" ? "default" : "outline"} asChild>
                  <Link to={focusTimelineLink}>Timeline</Link>
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" asChild>
                <Link to="/documents">Сбросить фокус</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardContent className="py-6">
          <ErrorState error={error ?? undefined} onRetry={() => void list()} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка документов" /> : null}
          {!loading && !error && items.length === 0 ? <EmptyState title="Документы не найдены" description="Создайте первый документ или измените фильтры." /> : null}
          <DocumentTable onSelect={setSelectedDocument} />
        </CardContent>
      </Card>
      {selectedDocument && <DocumentPreview document={selectedDocument} initialTab={focusedView === "timeline" ? "timeline" : "preview"} />}
    </div>
  );
};

export default DocumentsPage;
