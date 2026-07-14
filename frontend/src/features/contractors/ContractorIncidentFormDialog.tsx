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
import { Textarea } from "@/components/ui/textarea";
import { SEVERITY_LABELS, SEVERITY_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { IncidentSeverity } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  onSubmitted?: () => void;
}

export const ContractorIncidentFormDialog = ({ trigger, contractorId, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [incidentType, setIncidentType] = useState("");
  const [severity, setSeverity] = useState<IncidentSeverity>("medium");
  const [occurredAt, setOccurredAt] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!open) return;
    setIncidentType("");
    setSeverity("medium");
    setOccurredAt("");
    setDescription("");
  }, [open]);

  const onSubmit = async () => {
    if (!incidentType.trim()) {
      toast.error("Укажите тип инцидента");
      return;
    }
    if (!occurredAt) {
      toast.error("Укажите дату и время");
      return;
    }
    setSubmitting(true);
    try {
      await contractorsApi.createIncident({
        contractor_id: contractorId,
        incident_type: incidentType.trim(),
        severity,
        occurred_at: new Date(occurredAt).toISOString(),
        description: description || null
      });
      toast.success("Инцидент зарегистрирован");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить инцидент");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый инцидент подрядчика</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="inc-type">Тип инцидента</Label>
            <Input id="inc-type" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="inc-severity">Тяжесть</Label>
              <select id="inc-severity" className="h-10 w-full rounded-md border px-3" value={severity} onChange={(e) => setSeverity(e.target.value as IncidentSeverity)}>
                {SEVERITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {SEVERITY_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="inc-date">Дата и время</Label>
              <Input id="inc-date" type="datetime-local" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="inc-desc">Описание</Label>
            <Textarea id="inc-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
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
