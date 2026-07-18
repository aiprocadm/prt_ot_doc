export const SYNC_STATES = ["online", "queued", "syncing", "conflict", "failed"] as const;
export type SyncState = (typeof SYNC_STATES)[number];

export const syncStateLabel: Record<SyncState, string> = {
  online: "online",
  queued: "queued",
  syncing: "syncing",
  conflict: "conflict",
  failed: "failed"
};

export const resolveSyncState = ({
  online,
  loading,
  hasConflict,
  hasError
}: {
  online: boolean;
  loading: boolean;
  hasConflict: boolean;
  hasError: boolean;
}): SyncState => {
  if (hasConflict) return "conflict";
  if (hasError) return "failed";
  if (!online) return "queued";
  if (loading) return "syncing";
  return "online";
};

export type SyncTelemetryEvent =
  | { type: "sync_state_changed"; state: SyncState; screen: string }
  | { type: "sync_conflict_detected"; conflictCode: string; entityType: string }
  | { type: "sync_conflict_resolved"; strategy: "server_wins" | "client_retry"; batchId: string }
  | { type: "sync_error"; screen: string; message: string };

export const emitSyncTelemetry = (event: SyncTelemetryEvent) => {
  const enriched = {
    ...event,
    at: new Date().toISOString()
  };
  window.dispatchEvent(new CustomEvent("pwa:sync-telemetry", { detail: enriched }));
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.info("[sync-telemetry]", enriched);
  }
};
