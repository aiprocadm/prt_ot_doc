import { Badge } from "@/components/ui/badge";

const statusColors: Record<string, "default" | "secondary" | "destructive"> = {
  active: "default",
  ready: "default",
  published: "default",
  draft: "secondary",
  generating: "secondary",
  processing: "secondary",
  queued: "secondary",
  open: "secondary",
  in_progress: "secondary",
  done: "default",
  ok: "default",
  warning: "secondary",
  critical: "destructive",
  error: "destructive",
  failed: "destructive",
  cancelled: "destructive",
  archived: "destructive"
};

export const StatusBadge = ({ status }: { status?: string | null }) => {
  if (!status) return null;
  const variant = statusColors[status] ?? "secondary";
  return <Badge variant={variant}>{status}</Badge>;
};
