import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { ADMISSION_STATUS_LABELS, DOC_TYPE_LABELS, EXPIRY_BADGE_VARIANT, EXPIRY_LABELS } from "@/pages/contractors/contractorsVocab";
import type { AdmissionVerdict, ContractorEmployee, DocumentChecklistItem } from "@/types/dto/contractors";

interface Props {
  employee: ContractorEmployee;
  trigger: ReactNode;
  onAdmitted?: () => void;
}

const extractViolations = (err: unknown): string[] => {
  const details = (err as { details?: { details?: Array<{ violations?: unknown[] }> } })?.details;
  const entries = details?.details ?? [];
  const all = entries.flatMap((e) => e.violations ?? []);
  return all.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
};

export const EmployeeAdmissionDialog = ({ employee, trigger, onAdmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [readiness, setReadiness] = useState<AdmissionVerdict | null>(null);
  const [checklist, setChecklist] = useState<DocumentChecklistItem[]>([]);
  const [blockedViolations, setBlockedViolations] = useState<string[]>([]);
  const [verdict, setVerdict] = useState<AdmissionVerdict | null>(null);

  useEffect(() => {
    if (!open) return;
    setBlockedViolations([]);
    setVerdict(null);
    setLoading(true);
    Promise.all([contractorsApi.getEmployeeReadiness(employee.id), contractorsApi.getEmployeeChecklist(employee.id)])
      .then(([r, c]) => {
        setReadiness(r);
        setChecklist(c.items ?? []);
      })
      .catch((err) => toast.error((err as { message?: string })?.message ?? "Не удалось загрузить готовность"))
      .finally(() => setLoading(false));
  }, [open, employee.id]);

  const onAdmit = async () => {
    setSubmitting(true);
    setBlockedViolations([]);
    try {
      const result = await contractorsApi.admitEmployee(employee.id);
      setVerdict(result);
      toast.success(ADMISSION_STATUS_LABELS[result.status] ?? "Допущен");
      onAdmitted?.();
    } catch (err) {
      const e = err as { status?: number; code?: string; message?: string };
      if (e.status === 409 || e.code === "requirements_not_met") {
        const violations = extractViolations(err);
        setBlockedViolations(violations.length ? violations : ["Не выполнены требования допуска"]);
      } else if (e.status === 404) {
        toast.error("Сотрудник не найден");
        setOpen(false);
      } else {
        toast.error(e.message ?? "Не удалось выполнить допуск");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Допуск: {employee.full_name}</DialogTitle>
          <DialogDescription>Проверка готовности документов и оформление допуска сотрудника.</DialogDescription>
        </DialogHeader>

        {loading ? <p className="text-sm text-muted-foreground">Загрузка готовности...</p> : null}

        {!loading && readiness && !verdict ? (
          <div className="space-y-1 text-sm">
            <div>
              Готовность:{" "}
              <Badge variant={readiness.status === "allowed" ? "default" : readiness.status === "blocked" ? "destructive" : "secondary"}>
                {ADMISSION_STATUS_LABELS[readiness.status] ?? readiness.status}
              </Badge>
            </div>
            {readiness.warnings.map((w) => (
              <p key={w} className="text-yellow-700">
                {w}
              </p>
            ))}
            {readiness.violations.map((v) => (
              <p key={v} className="text-destructive">
                {v}
              </p>
            ))}
          </div>
        ) : null}

        {!loading ? (
          <div className="space-y-2">
            <div className="text-sm font-medium">Документы по требованиям</div>
            {checklist.length === 0 ? (
              <p className="text-sm text-muted-foreground">Требования к документам не настроены.</p>
            ) : (
              <ul className="divide-y rounded-md border text-sm">
                {checklist.map((item) => (
                  <li key={`${item.doc_type}-${item.scope}`} className="flex items-center justify-between gap-2 p-2">
                    <span>
                      {DOC_TYPE_LABELS[item.doc_type] ?? item.doc_type}
                      {item.mandatory ? " *" : ""}
                    </span>
                    <Badge variant={EXPIRY_BADGE_VARIANT[item.status]}>{EXPIRY_LABELS[item.status]}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {blockedViolations.length > 0 ? (
          <div role="alert" className="rounded-md border border-destructive bg-destructive/10 p-2 text-sm">
            <div className="mb-1 font-medium text-destructive">Допуск невозможен:</div>
            <ul className="list-inside list-disc">
              {blockedViolations.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {verdict ? <p className="text-sm text-green-700">{ADMISSION_STATUS_LABELS[verdict.status]}</p> : null}

        <DialogFooter>
          <Button onClick={() => void onAdmit()} disabled={submitting || loading}>
            {submitting ? "Проверка..." : "Допустить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
