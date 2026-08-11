import { Badge } from "@/components/ui/badge";

const slaStyles: Record<string, "default" | "secondary" | "destructive"> = {
  ok: "default",
  warning: "secondary",
  overdue: "destructive",
};

export const SlaIndicator = ({
  status,
  label,
}: {
  status: "ok" | "warning" | "overdue";
  label: string;
}) => <Badge variant={slaStyles[status]}>{label}</Badge>;
