import { useCallback, useEffect, useState } from "react";

import { opsApi, type CorrectiveActionDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConflictInboxCard } from "@/components/pwa/ConflictInboxCard";
import { MobileFieldModeCard } from "@/components/pwa/MobileFieldModeCard";
import { SyncStatusChips } from "@/components/pwa/SyncStatusChips";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { emitSyncTelemetry, resolveSyncState } from "@/pwa/sync";
import { formatDate } from "@/utils/datetime";

const CorrectiveActionsPage = () => {
  const loadActions = useCallback(() => opsApi.getCorrectiveActions(), []);
  const { data: items, loading, error, reload } = useAsyncResource<CorrectiveActionDto[]>({
    loader: loadActions,
    initialData: [],
    errorMessage: "Не удалось загрузить CAPA"
  });
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [hasConflict, setHasConflict] = useState(false);
  const syncState = resolveSyncState({ online, loading, hasConflict, hasError: Boolean(error) });

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    emitSyncTelemetry({ type: "sync_state_changed", state: syncState, screen: "corrective_actions" });
    if (error?.message) {
      emitSyncTelemetry({ type: "sync_error", screen: "corrective_actions", message: error.message });
    }
  }, [error?.message, syncState]);

  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.id, item.title, item.status, item.source_type, item.action_type, item.effectiveness_status, item.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Корректирующие действия"
        description="Операционный реестр CAPA на основе backend `/corrective-actions` с реальными полями сроков, статусов и эффективности, единым интерфейсом и пагинацией."
      />
      <div className="grid gap-3 lg:grid-cols-3">
        <Card>
          <CardContent className="pt-4">
            <SyncStatusChips state={syncState} />
          </CardContent>
        </Card>
        <ConflictInboxCard onConflictStateChange={setHasConflict} />
        <MobileFieldModeCard />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Корректирующие и предупреждающие действия</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка реестра CAPA" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Действия не найдены" description={registry.query ? "Попробуйте другой запрос." : "В текущем тенанте пока нет корректирующих действий."} />
          ) : null}
          {!loading && !error && registry.total > 0 ? (
            <RegistryTable
              columns={[
                {
                  accessorKey: "id",
                  header: "ID",
                  cell: ({ row }) => <span className="font-medium">{row.original.id.slice(0, 8)}</span>
                },
                {
                  accessorKey: "title",
                  header: "Мероприятие",
                  cell: ({ row }) => (
                    <div>
                      <div className="font-medium">{row.original.title}</div>
                      <div className="text-xs text-muted-foreground">{row.original.action_type}</div>
                    </div>
                  )
                },
                {
                  id: "source",
                  header: "Источник",
                  cell: ({ row }) => (
                    <div>
                      <div>{row.original.source_type}</div>
                      <div className="text-xs text-muted-foreground">{row.original.source_id.slice(0, 8)}</div>
                    </div>
                  )
                },
                {
                  accessorKey: "due_date",
                  header: "Срок",
                  cell: ({ row }) => formatDate(row.original.due_date) || "—"
                },
                {
                  accessorKey: "status",
                  header: "Статус",
                  cell: ({ row }) => <StatusBadge status={row.original.status} />
                },
                {
                  accessorKey: "effectiveness_status",
                  header: "Эффективность",
                  cell: ({ row }) => row.original.effectiveness_status ?? "—"
                }
              ]}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по мероприятию, source, status"
              caption="CAPA registry with tenant-aware live data"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CorrectiveActionsPage;
