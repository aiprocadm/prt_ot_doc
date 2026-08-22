import { useCallback, useEffect, useState } from "react";

import { pwaSyncApi, type PwaConflictItem } from "@/api/pwaSync";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { emitSyncTelemetry } from "@/pwa/sync";

export const ConflictInboxCard = ({
  onConflictStateChange,
}: {
  onConflictStateChange?: (hasConflict: boolean) => void;
}) => {
  const [items, setItems] = useState<PwaConflictItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const bootstrap = await pwaSyncApi.getBootstrap();
      const conflicts = bootstrap.offline_queue?.failed_conflicts ?? [];
      setItems(conflicts);
      onConflictStateChange?.(conflicts.length > 0);
      conflicts.forEach((item) =>
        emitSyncTelemetry({
          type: "sync_conflict_detected",
          conflictCode: item.conflict_code,
          entityType: item.entity_type,
        }),
      );
    } catch {
      // No tenant, offline, or server error — card is best-effort; avoid unhandled rejections in tests/embedded.
      setItems([]);
      onConflictStateChange?.(false);
    } finally {
      setLoading(false);
    }
  }, [onConflictStateChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = async (
    batchId: string,
    strategy: "server_wins" | "client_retry",
  ) => {
    await pwaSyncApi.resolveConflict(batchId, strategy);
    emitSyncTelemetry({ type: "sync_conflict_resolved", strategy, batchId });
    await load();
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Conflict inbox</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <p className="text-xs text-muted-foreground">
            Обновление конфликтов…
          </p>
        ) : null}
        {!loading && items.length === 0 ? (
          <p className="text-xs text-muted-foreground">Конфликтов нет.</p>
        ) : null}
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-md border p-3 text-sm space-y-2"
          >
            <div className="font-medium">{item.entity_type}</div>
            <div className="text-xs text-muted-foreground">
              {item.conflict_code}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className="min-h-11 px-4"
                onClick={() => void resolve(item.id, "server_wins")}
              >
                Server wins
              </Button>
              {/* Кнопка живёт в ПОВТОРЯЮЩЕЙСЯ строке конфликта: primary здесь
                  означало бы «основных действий столько, сколько конфликтов»
                  (прецедент BillingPage/OutboxPage). */}
              <Button
                size="sm"
                variant="outline"
                className="min-h-11 px-4"
                onClick={() => void resolve(item.id, "client_retry")}
              >
                Retry client
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};
