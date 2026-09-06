import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  MONITORING_PERIODICITY_TITLES,
  ecologyApi,
  type EmissionSourceDto,
  type MonitoringPlanItemDto,
} from "@/api/ecology";
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
  ecologyMonitoringPlanFormSchema,
  type EcologyMonitoringPlanFormValues,
} from "@/types/forms/ecologyMonitoring";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyMonitoringPlanFormValues = {
  source_id: "",
  substance: "",
  periodicity_months: "",
  next_due_on: "",
  method: "",
  laboratory: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyMonitoringPlanFormValues> = {
  source_id: "source_id",
  substance: "substance",
  periodicity_months: "periodicity_months",
  next_due_on: "next_due_on",
  method: "method",
  laboratory: "laboratory",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyMonitoringPlanFormDialogProps {
  trigger: ReactNode;
  sources: EmissionSourceDto[];
  initialData?: MonitoringPlanItemDto;
  onSubmitted?: (item: MonitoringPlanItemDto) => void;
}

/**
 * Форма строки плана-графика ПЭК (разд. 55.2, срез-101).
 *
 * Четыре поля на первом уровне: источник, вещество, периодичность и дата
 * ближайшего замера; метод, лаборатория и заметки — под «Дополнительно».
 *
 * ГРАНИЦА: периодичность берётся из утверждённой программы ПЭК — платформа её
 * не назначает и не подсказывает «правильное» число. Типовые сроки (месяц,
 * квартал, полугодие, год) есть в подсказке у поля, но выбрать можно любой от
 * 1 до 60 месяцев, как принимает сервер.
 */
export const EcologyMonitoringPlanFormDialog = ({
  trigger,
  sources,
  initialData,
  onSubmitted,
}: EcologyMonitoringPlanFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyMonitoringPlanFormValues>({
    resolver: zodResolver(ecologyMonitoringPlanFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        source_id: initialData.source_id,
        substance: initialData.substance,
        periodicity_months: String(initialData.periodicity_months),
        next_due_on: initialData.next_due_on,
        method: initialData.method ?? "",
        laboratory: initialData.laboratory ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyMonitoringPlanFormValues) => {
    const common = {
      substance: values.substance.trim(),
      periodicity_months: Number(values.periodicity_months),
      next_due_on: values.next_due_on,
      method: orNull(values.method),
      laboratory: orNull(values.laboratory),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateMonitoringPlanItem(initialData.id, common)
        : await ecologyApi.createMonitoringPlanItem({
            source_id: values.source_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Строка плана обновлена" : "Строка плана внесена");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить строку плана");
      } else {
        toast.error("Не удалось сохранить строку плана");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyMonitoringPlanFormValues) => {
    const message = form.formState.errors[name]?.message;
    return message ? (
      <p className="text-xs text-destructive">{message}</p>
    ) : null;
  };

  const periodicityHint = Object.entries(MONITORING_PERIODICITY_TITLES)
    .map(([months, title]) => `${months} — ${title}`)
    .join(", ");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Изменить строку плана" : "Внести строку плана ПЭК"}
          </DialogTitle>
          <DialogDescription>
            Периодичность берётся из утверждённой программы ПЭК: платформа её не
            назначает. Внесение замера по этой строке само сдвинет плановую дату
            вперёд.
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
              <Label htmlFor="eco-plan-source">Источник выбросов</Label>
              {/* Источник у строки плана не меняют: ручка правки его не
                  принимает, а «переезд» строки на другой источник — это
                  другая строка графика. */}
              <select
                id="eco-plan-source"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("source_id")}
              >
                <option value="">— Выберите источник —</option>
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    №{source.source_number} · {source.name}
                  </option>
                ))}
              </select>
              {fieldError("source_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-plan-substance">Вещество</Label>
              <Input
                id="eco-plan-substance"
                placeholder="напр. Азота диоксид"
                {...form.register("substance")}
              />
              {fieldError("substance")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-plan-periodicity">
                Периодичность, месяцев
              </Label>
              <Input
                id="eco-plan-periodicity"
                type="number"
                min={1}
                max={60}
                inputMode="numeric"
                title={`Типовые сроки: ${periodicityHint}`}
                {...form.register("periodicity_months")}
              />
              {fieldError("periodicity_months")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-plan-due">Ближайший замер</Label>
              <Input
                id="eco-plan-due"
                type="date"
                {...form.register("next_due_on")}
              />
              {fieldError("next_due_on")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Метод, лаборатория и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="eco-plan-method">Метод</Label>
                  <Input
                    id="eco-plan-method"
                    placeholder="методика измерений"
                    {...form.register("method")}
                  />
                  {fieldError("method")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-plan-lab">Лаборатория</Label>
                  <Input
                    id="eco-plan-lab"
                    placeholder="кто проводит замер"
                    {...form.register("laboratory")}
                  />
                  {fieldError("laboratory")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-plan-notes">Заметки</Label>
                <Textarea
                  id="eco-plan-notes"
                  rows={3}
                  placeholder="условия программы ПЭК, особенности"
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
