import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  PC_PLAN_STATUS_TITLES,
  industrialSafetyApi,
  type PcPlanDto,
} from "@/api/industrialSafety";
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
import {
  pcPlanFormSchema,
  type PcPlanFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: PcPlanFormValues = {
  year: String(new Date().getFullYear()),
  title: "",
  status: "draft",
  responsible: "",
  approved_on: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof PcPlanFormValues> = {
  year: "year",
  title: "title",
  status: "status",
  responsible: "responsible",
  approved_on: "approved_on",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface PcPlanFormDialogProps {
  trigger: ReactNode;
  initialData?: PcPlanDto;
  onSubmitted?: (plan: PcPlanDto) => void;
}

/**
 * Форма плана производственного контроля (разд. 54.2, срез-106).
 *
 * Четыре поля на первом уровне: год, название, состояние и ответственный за
 * осуществление ПК; дата утверждения и заметки — под «Дополнительно».
 *
 * ГРАНИЦА: платформа сообщает ФАКТ отсутствия плана, но не объявляет это
 * нарушением — обязанность зависит от того, эксплуатирует ли организация ОПО.
 */
export const PcPlanFormDialog = ({
  trigger,
  initialData,
  onSubmitted,
}: PcPlanFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<PcPlanFormValues>({
    resolver: zodResolver(pcPlanFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        year: String(initialData.year),
        title: initialData.title,
        status: initialData.status,
        responsible: initialData.responsible ?? "",
        approved_on: initialData.approved_on ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: PcPlanFormValues) => {
    const body = {
      year: Number(values.year),
      title: values.title.trim(),
      status: values.status,
      responsible: orNull(values.responsible),
      approved_on: orNull(values.approved_on),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await industrialSafetyApi.updatePcPlan(initialData.id, body)
        : await industrialSafetyApi.createPcPlan(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "План обновлён" : "План заведён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить план");
      } else {
        toast.error("Не удалось сохранить план");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof PcPlanFormValues) => {
    const message = form.formState.errors[name]?.message;
    return message ? (
      <p className="text-xs text-destructive">{message}</p>
    ) : null;
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Изменить план ПК" : "Завести план ПК"}
          </DialogTitle>
          <DialogDescription>
            План производственного контроля — годовой документ для надзора.
            Нужен ли он вашей организации, зависит от того, эксплуатирует ли она
            ОПО: платформа показывает факт, но нарушением его не объявляет.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast уже показан в onSubmit */
            }
          })}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="pc-plan-year">Год</Label>
              <Input
                id="pc-plan-year"
                type="number"
                min={2000}
                max={2100}
                inputMode="numeric"
                {...form.register("year")}
              />
              {fieldError("year")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="pc-plan-status">Состояние</Label>
              <select
                id="pc-plan-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(PC_PLAN_STATUS_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("status")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="pc-plan-title">План</Label>
            <Input
              id="pc-plan-title"
              placeholder="напр. План производственного контроля на 2026 год"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="space-y-2">
            <Label htmlFor="pc-plan-responsible">
              Ответственный за осуществление ПК
            </Label>
            <Input
              id="pc-plan-responsible"
              placeholder="назначается приказом"
              {...form.register("responsible")}
            />
            {fieldError("responsible")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Утверждение и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pc-plan-approved">Утверждён</Label>
                <Input
                  id="pc-plan-approved"
                  type="date"
                  {...form.register("approved_on")}
                />
                {fieldError("approved_on")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="pc-plan-notes">Заметки</Label>
                <Textarea
                  id="pc-plan-notes"
                  rows={3}
                  placeholder="реквизиты приказа, особенности"
                  {...form.register("notes")}
                />
                {fieldError("notes")}
              </div>
            </div>
          </details>
          <DialogFooter>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
