import type { ReactElement } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  RefreshCw,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { SyncState } from "@/pwa/sync";

const iconByState: Record<SyncState, ReactElement> = {
  online: <CheckCircle2 className="h-3.5 w-3.5" />,
  queued: <WifiOff className="h-3.5 w-3.5" />,
  syncing: <RefreshCw className="h-3.5 w-3.5 animate-spin" />,
  conflict: <AlertCircle className="h-3.5 w-3.5" />,
  failed: <Clock3 className="h-3.5 w-3.5" />,
};

const variantByState: Record<
  SyncState,
  "default" | "secondary" | "destructive" | "outline"
> = {
  online: "default",
  queued: "secondary",
  syncing: "outline",
  conflict: "destructive",
  failed: "destructive",
};

export const SyncStatusChips = ({ state }: { state: SyncState }) => (
  <div className="flex items-center gap-2">
    <Badge
      variant={variantByState[state]}
      className="inline-flex items-center gap-1"
    >
      {iconByState[state]}
      {state}
    </Badge>
    <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground">
      <span>States:</span>
      <span>online / queued / syncing / conflict / failed</span>
    </div>
  </div>
);
