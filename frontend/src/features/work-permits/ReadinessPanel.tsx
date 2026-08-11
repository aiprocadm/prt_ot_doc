import type { ReadinessReportDto } from "@/types/dto/workPermits";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";

const VIOLATION_LABELS: Record<string, string> = {
  permit_missing: "нет личного допуска",
  permit_expired: "просрочен личный допуск",
  medical_missing: "нет медосмотра",
  medical_expired: "просрочен медосмотр",
  training_missing: "нет обучения",
  training_expired: "просрочено обучение",
};

export const ReadinessPanel = ({
  report,
  nameOf,
}: {
  report: ReadinessReportDto | null;
  nameOf: (personId: string) => string;
}) => {
  if (!report) return <p className="text-sm text-muted-foreground">Готовность не загружена</p>;
  if (report.ok)
    return <p className="text-sm text-emerald-600">Бригада готова — все допуски действуют</p>;
  return (
    <ul className="space-y-1 text-sm text-destructive">
      {report.violations.map((v, i) => (
        <li key={i}>
          {nameOf(v.person_id)} ({labelOf(MEMBER_ROLE_LABELS, v.role)}) —{" "}
          {VIOLATION_LABELS[v.code] ?? v.code}
        </li>
      ))}
    </ul>
  );
};
