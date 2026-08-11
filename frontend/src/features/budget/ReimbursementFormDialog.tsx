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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type {
  BudgetReimbursementCreateInput,
  BudgetReimbursementDto,
  BudgetReimbursementUpdateInput,
} from "@/types/dto/budget";

interface Props {
  trigger: ReactNode;
  initialData?: BudgetReimbursementDto;
  onSubmitted?: () => void;
}

const emptyForm = {
  title: "",
  period_start: "",
  period_end: "",
  requested_amount: "",
  reference: "",
  notes: "",
};

export const ReimbursementFormDialog = ({
  trigger,
  initialData,
  onSubmitted,
}: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            title: initialData.title,
            period_start: initialData.period_start,
            period_end: initialData.period_end,
            requested_amount: String(initialData.requested_amount),
            reference: initialData.reference ?? "",
            notes: initialData.notes ?? "",
          }
        : emptyForm,
    );
  }, [open, initialData]);

  const set = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = async () => {
    if (!form.title.trim()) {
      toast.error("Укажите название заявки");
      return;
    }
    if (!form.period_start || !form.period_end) {
      toast.error("Укажите период заявки");
      return;
    }
    if (!isEdit && form.requested_amount.trim() === "") {
      toast.error("Укажите запрашиваемую сумму");
      return;
    }
    setSubmitting(true);
    try {
      if (isEdit && initialData) {
        // Только изменённые поля: PATCH принимает любое подмножество и разрешён лишь в draft.
        const payload: BudgetReimbursementUpdateInput = {};
        const trimmedTitle = form.title.trim();
        if (trimmedTitle !== initialData.title) payload.title = trimmedTitle;
        if (form.period_start !== initialData.period_start)
          payload.period_start = form.period_start;
        if (form.period_end !== initialData.period_end)
          payload.period_end = form.period_end;
        if (
          form.requested_amount.trim() !== "" &&
          Number(form.requested_amount) !== initialData.requested_amount
        ) {
          payload.requested_amount = Number(form.requested_amount);
        }
        const normalizedReference = form.reference.trim() || null;
        if (normalizedReference !== initialData.reference)
          payload.reference = normalizedReference;
        const normalizedNotes = form.notes.trim() || null;
        if (normalizedNotes !== initialData.notes)
          payload.notes = normalizedNotes;
        await budgetApi.updateReimbursement(initialData.id, payload);
        toast.success("Заявка обновлена");
      } else {
        const payload: BudgetReimbursementCreateInput = {
          title: form.title.trim(),
          period_start: form.period_start,
          period_end: form.period_end,
          requested_amount: Number(form.requested_amount),
          reference: form.reference.trim() || null,
          notes: form.notes.trim() || null,
        };
        await budgetApi.createReimbursement(payload);
        toast.success("Заявка создана");
      }
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error(
        (err as { message?: string })?.message ?? "Не удалось сохранить заявку",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Редактировать заявку" : "Новая заявка"}
          </DialogTitle>
          <DialogDescription>
            Заявка на возмещение расходов на охрану труда из средств СФР.
            Создаётся черновиком.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="r-title">Название</Label>
            <Input
              id="r-title"
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="r-period-start">Период с</Label>
              <Input
                id="r-period-start"
                type="date"
                value={form.period_start}
                onChange={(e) => set("period_start", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="r-period-end">Период по</Label>
              <Input
                id="r-period-end"
                type="date"
                value={form.period_end}
                onChange={(e) => set("period_end", e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="r-requested">Запрашиваемая сумма</Label>
            <Input
              id="r-requested"
              type="number"
              value={form.requested_amount}
              onChange={(e) => set("requested_amount", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="r-reference">Номер в СФР</Label>
            <Input
              id="r-reference"
              value={form.reference}
              onChange={(e) => set("reference", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="r-notes">Примечания</Label>
            <Textarea
              id="r-notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
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
