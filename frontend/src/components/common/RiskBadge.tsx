import { Badge } from "@/components/ui/badge";

const riskStyles: Record<string, "default" | "secondary" | "destructive"> = {
  low: "secondary",
  medium: "default",
  high: "destructive",
  critical: "destructive",
};

export const RiskBadge = ({ level }: { level?: string | null }) => {
  if (!level) return null;
  return <Badge variant={riskStyles[level] ?? "secondary"}>{level}</Badge>;
};
