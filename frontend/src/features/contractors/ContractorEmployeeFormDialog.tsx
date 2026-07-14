import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COMPLIANCE_STATUS_LABELS, COMPLIANCE_STATUS_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { ComplianceStatus, ContractorEmployee } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  initialData?: ContractorEmployee;
  onSubmitted?: () => void;
}

const StatusSelect = ({
  id,
  label,
  value,
  onChange
}: {
  id: string;
  label: string;
  value: ComplianceStatus;
  onChange: (v: ComplianceStatus) => void;
}) => (
  <div className="space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <select id={id} className="h-10 w-full rounded-md border px-3" value={value} onChange={(e) => onChange(e.target.value as ComplianceStatus)}>
      {COMPLIANCE_STATUS_OPTIONS.map((s) => (
        <option key={s} value={s}>
          {COMPLIANCE_STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  </div>
);

export const ContractorEmployeeFormDialog = ({ trigger, contractorId, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(initialData);
  const [fullName, setFullName] = useState("");
  const [position, setPosition] = useState("");
  const [access, setAccess] = useState<ComplianceStatus>("pending");
  const [training, setTraining] = useState<ComplianceStatus>("pending");
  const [medical, setMedical] = useState<ComplianceStatus>("pending");

  useEffect(() => {
    if (!open) return;
    setFullName(initialData?.full_name ?? "");
    setPosition(initialData?.position ?? "");
    setAccess(initialData?.access_status ?? "pending");
    setTraining(initialData?.training_status ?? "pending");
    setMedical(initialData?.medical_status ?? "pending");
  }, [open, initialData]);

  const onSubmit = async () => {
    if (!isEdit && !fullName.trim()) {
      toast.error("Укажите ФИО сотрудника");
      return;
    }
    setSubmitting(true);
    try {
      if (initialData) {
        await contractorsApi.updateEmployee(initialData.id, {
          position: position || null,
          access_status: access,
          training_status: training,
          medical_status: medical
        });
      } else {
        await contractorsApi.createEmployee({
          contractor_id: contractorId,
          full_name: fullName.trim(),
          position: position || null,
          access_status: access,
          training_status: training,
          medical_status: medical
        });
      }
      toast.success(isEdit ? "Сотрудник обновлён" : "Сотрудник добавлен");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить сотрудника");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать сотрудника" : "Новый сотрудник подрядчика"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!isEdit ? (
            <div className="space-y-2">
              <Label htmlFor="emp-name">ФИО</Label>
              <Input id="emp-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="emp-position">Должность</Label>
            <Input id="emp-position" value={position} onChange={(e) => setPosition(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <StatusSelect id="emp-access" label="Допуск" value={access} onChange={setAccess} />
            <StatusSelect id="emp-training" label="Обучение" value={training} onChange={setTraining} />
            <StatusSelect id="emp-medical" label="Медосмотр" value={medical} onChange={setMedical} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
