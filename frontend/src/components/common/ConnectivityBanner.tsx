import { RefreshCcw, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export const ConnectivityBanner = () => {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      setLastSyncAt(new Date().toISOString());
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (online) {
    return (
      <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-xs text-emerald-900">
        Sync status: online{lastSyncAt ? ` · last sync ${new Date(lastSyncAt).toLocaleTimeString()}` : ""}. Mobile/PWA critical flows can retry background sync safely.
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950">
      <div className="flex items-center gap-2">
        <WifiOff className="h-4 w-4" />
        <span>You are offline. Draft-friendly screens should keep local progress and retry sync when connection returns.</span>
      </div>
      <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
        <RefreshCcw className="mr-2 h-4 w-4" /> Retry sync
      </Button>
    </div>
  );
};
