import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { budgetApi } from "@/api/budget";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { BUDGET_DOMAIN_LABELS } from "@/pages/budget/budgetVocab";
import type {
  BudgetDomain,
  SafetyBudgetCreateInput,
  SafetyBudgetDto,
  SafetyBudgetUpdateInput
} from "@/types/dto/budget";

const BUDGET_DOMAINS: BudgetDomain[] = ["training", "medical", "events"];

interface Props {
  trigger: ReactNode;
  initialData?: SafetyBudgetDto;
  onSubmitted?: () => void;
}

const emptyForm = {
  name: "",
  domain: "training" as BudgetDomain,
  period_start: "",
  period_end: "",
  planned_amount: "",
  notes: ""
};

export const BudgetFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            name: initialData.name,
            domain: initialData.domain,
            period_start: initialData.period_start,
            period_end: initialData.period_end,
            planned_amount: String(initialData.planned_amount),
            notes: initialData.notes ?? ""
          }
        : emptyForm
    );
  }, [open, initialData]);

  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = async () => {
    if (!form.name.trim()) {
      toast.error("Укажите название бюджета");
      return;
    }
    if (!form.period_start || !form.period_end) {
      toast.error("Укажите период бюджета");
      return;
    }
    if (!isEdit && form.planned_amount.trim() === "") {
      toast.error("Укажите плановую сумму");
      return;
    }
    setSubmitting(true);
    try {
      if (isEdit && initialData) {
        // Только изменённые поля: domain иммутабелен при редактировании (не отправляем).
        const payload: SafetyBudgetUpdateInput = {};
        const trimmedName = form.name.trim();
        if (trimmedName !== initialData.name) payload.name = trimmedName;
        if (form.period_start !== initialData.period_start) payload.period_start = form.period_start;
        if (form.period_end !== initialData.period_end) payload.period_end = form.period_end;
        if (form.planned_amount.trim() !== "" && Number(form.planned_amount) !== initialData.planned_amount) {
          payload.planned_amount = Number(form.planned_amount);
        }
        const normalizedNotes = form.notes.trim() || null;
        if (normalizedNotes !== initialData.notes) payload.notes = normalizedNotes;
        await budgetApi.updateBudget(initialData.id, payload);
        toast.success("Бюджет обновлён");
      } else {
        const payload: SafetyBudgetCreateInput = {
          name: form.name.trim(),
          domain: form.domain,
          period_start: form.period_start,
          period_end: form.period_end,
          planned_amount: Number(form.planned_amount),
          notes: form.notes.trim() || null
        };
        await budgetApi.createBudget(payload);
        toast.success("Бюджет создан");
      }
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить бюджет");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать бюджет" : "Новый бюджет"}</DialogTitle>
          <DialogDescription>Плановая сумма и период бюджета по домену безопасности.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="b-name">Название</Label>
            <Input id="b-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="b-domain">Домен</Label>
            <select
              id="b-domain"
              className="h-10 w-full rounded-md border px-3"
              value={form.domain}
              disabled={isEdit}
              onChange={(e) => set("domain", e.target.value)}
            >
              {BUDGET_DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {BUDGET_DOMAIN_LABELS[d]}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="b-period-start">Период с</Label>
              <Input
                id="b-period-start"
                type="date"
                value={form.period_start}
                onChange={(e) => set("period_start", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="b-period-end">Период по</Label>
              <Input
                id="b-period-end"
                type="date"
                value={form.period_end}
                onChange={(e) => set("period_end", e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="b-planned">Плановая сумма</Label>
            <Input
              id="b-planned"
              type="number"
              value={form.planned_amount}
              onChange={(e) => set("planned_amount", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="b-notes">Примечания</Label>
            <Textarea id="b-notes" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
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
