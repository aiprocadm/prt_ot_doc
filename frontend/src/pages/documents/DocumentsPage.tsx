import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { ListStateGuard } from "@/components/common/ListStateGuard";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { SectionErrorBoundary } from "@/components/common/SectionErrorBoundary";
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
import { ROUTES } from "@/router/routes";
import { entityCardLink } from "@/utils/workspaceNavigation";

const EMPTY_DOCUMENTS: DocumentDto[] = [];

const DocumentsPage = () => {
  const { list, items, pagination, loading, error, getById } =
    useDocumentsStore();
  const [selectedDocument, setSelectedDocument] = useState<DocumentDto | null>(
    null,
  );
  const [searchParams] = useSearchParams();
  const { can } = useAbility();
  const canView = can(PERMISSIONS.DOCUMENT_VIEW);
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;
  const focusedView =
    searchParams.get("view") === "timeline" ? "timeline" : "summary";
  const safeItems = useMemo(
    () => (Array.isArray(items) ? items : EMPTY_DOCUMENTS),
    [items],
  );
  const safePagination = pagination ?? {
    page: 1,
    page_size: 10,
    total: safeItems.length,
  };

  const statusCounts = safeItems.reduce(
    (acc, document) => {
      if (!document?.status) {
        return acc;
      }
      acc[document.status] = (acc[document.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<DocumentDto["status"], number>,
  );

  useEffect(() => {
    if (canView) {
      list();
    }
  }, [canView, list]);

  useEffect(() => {
    if (!canView || !focusedEntityId) return;
    if (
      !["document", "document_version", "template_version"].includes(
        focusedEntityType ?? "",
      )
    )
      return;

    const existing = safeItems.find((doc) => doc.id === focusedEntityId);
    if (existing) {
      setSelectedDocument((prev) =>
        prev?.id === existing.id && prev.updated_at === existing.updated_at
          ? prev
          : existing,
      );
      return;
    }
    void getById(focusedEntityId).then((doc) => {
      if (doc) {
        setSelectedDocument((prev) =>
          prev?.id === doc.id && prev.updated_at === doc.updated_at
            ? prev
            : doc,
        );
      }
    });
  }, [canView, focusedEntityId, focusedEntityType, getById, safeItems]);

  const focusSummaryLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "summary"),
    [focusedEntityId, focusedEntityType],
  );
  const focusTimelineLink = useMemo(
    () => entityCardLink(focusedEntityType, focusedEntityId, "timeline"),
    [focusedEntityId, focusedEntityType],
  );

  if (!canView) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: ROUTES.DASHBOARD },
          { label: "Документы" },
        ]}
      />
      <RegistryPageHeader
        title="Документы"
        description="Все корпоративные документы, шаблоны и версии с контролем статуса и компании."
        actions={
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {loading ? "Обновление списка…" : "Данные актуальны"}
            </span>
            <PermissionGate permission={PERMISSIONS.DOCUMENT_CREATE}>
              <div className="flex items-center gap-2">
                <Button asChild variant="outline">
                  <Link to="/documents/quick-generate">Быстрая генерация</Link>
                </Button>
                <Button asChild>
                  <Link to="/documents/wizard">Создать документ</Link>
                </Button>
              </div>
            </PermissionGate>
          </div>
        }
        stats={[
          { label: "Всего документов", value: safePagination.total },
          { label: "Готовые (на странице)", value: statusCounts.ready ?? 0 },
          { label: "Черновики (на странице)", value: statusCounts.draft ?? 0 },
          { label: "Ошибки (на странице)", value: statusCounts.error ?? 0 },
        ]}
      />
      <SectionErrorBoundary>
        <PermissionGate permission={PERMISSIONS.DOCUMENT_CREATE}>
          <DocumentCreateWizard />
        </PermissionGate>
      </SectionErrorBoundary>
      {focusedEntityId &&
      ["document", "document_version", "template_version"].includes(
        focusedEntityType ?? "",
      ) ? (
        <Card>
          <CardContent className="py-4" data-testid="document-focus-card">
            <div className="text-sm font-semibold">
              Фокус документа из рабочего пространства
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {selectedDocument
                ? `${selectedDocument.name} · ${selectedDocument.status}`
                : `Документ ${focusedEntityId.slice(0, 8)} загружается...`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {focusSummaryLink ? (
                <Button
                  size="sm"
                  variant={focusedView === "summary" ? "default" : "outline"}
                  asChild
                >
                  <Link to={focusSummaryLink}>Сводка</Link>
                </Button>
              ) : null}
              {focusTimelineLink ? (
                <Button
                  size="sm"
                  variant={focusedView === "timeline" ? "default" : "outline"}
                  asChild
                >
                  <Link to={focusTimelineLink}>Хронология</Link>
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" asChild>
                <Link to="/documents">Сбросить фокус</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <SectionErrorBoundary>
        <Card>
          <CardContent className="py-6">
            <ListStateGuard
              error={error}
              loading={loading}
              itemsCount={safeItems.length}
              loadingLabel="Загрузка документов"
              emptyTitle="Документы не найдены"
              emptyDescription="Создайте первый документ или измените фильтры."
              onRetry={() => void list()}
            >
              <DocumentTable onSelect={setSelectedDocument} />
            </ListStateGuard>
          </CardContent>
        </Card>
      </SectionErrorBoundary>
      {selectedDocument ? (
        <SectionErrorBoundary>
          <DocumentPreview
            document={selectedDocument}
            initialTab={focusedView === "timeline" ? "timeline" : "preview"}
          />
        </SectionErrorBoundary>
      ) : null}
    </div>
  );
};

export default DocumentsPage;
