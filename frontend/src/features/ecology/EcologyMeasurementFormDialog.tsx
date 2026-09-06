import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  ecologyApi,
  type EmissionMeasurementDto,
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
  decimalToPayload,
  ecologyMeasurementFormSchema,
  type EcologyMeasurementFormValues,
} from "@/types/forms/ecologyMonitoring";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyMeasurementFormValues = {
  source_id: "",
  substance: "",
  measured_on: "",
  value_grams_per_second: "",
  plan_id: "",
  protocol_number: "",
  laboratory: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyMeasurementFormValues> = {
  source_id: "source_id",
  substance: "substance",
  measured_on: "measured_on",
  value_grams_per_second: "value_grams_per_second",
  plan_id: "plan_id",
  protocol_number: "protocol_number",
  laboratory: "laboratory",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyMeasurementFormDialogProps {
  trigger: ReactNode;
  sources: EmissionSourceDto[];
  planItems: MonitoringPlanItemDto[];
  initialData?: EmissionMeasurementDto;
  onSubmitted?: (measurement: EmissionMeasurementDto) => void;
}

/**
 * Форма замера ПЭК (разд. 55.2, срез-101).
 *
 * Четыре поля на первом уровне: источник, вещество, дата и результат в г/с;
 * строка плана, протокол, лаборатория и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: превышение считает сервер, сравнивая результат с внесённым
 * нормативом, — форма никакого вывода не делает и «допустимого» значения не
 * подсказывает. Строка плана необязательна (замер по предписанию бывает
 * внеплановым), но если её указать, сервер сам сдвинет плановую дату вперёд.
 * При правке источник, вещество и строка плана заперты: ручка PATCH их не
 * принимает — это уже другой замер.
 */
export const EcologyMeasurementFormDialog = ({
  trigger,
  sources,
  planItems,
  initialData,
  onSubmitted,
}: EcologyMeasurementFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyMeasurementFormValues>({
    resolver: zodResolver(ecologyMeasurementFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        source_id: initialData.source_id,
        substance: initialData.substance,
        measured_on: initialData.measured_on,
        value_grams_per_second: initialData.value_grams_per_second,
        plan_id: initialData.plan_id ?? "",
        protocol_number: initialData.protocol_number ?? "",
        laboratory: initialData.laboratory ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyMeasurementFormValues) => {
    const editable = {
      measured_on: values.measured_on,
      value_grams_per_second: decimalToPayload(values.value_grams_per_second),
      protocol_number: orNull(values.protocol_number),
      laboratory: orNull(values.laboratory),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateEmissionMeasurement(initialData.id, editable)
        : await ecologyApi.createEmissionMeasurement({
            source_id: values.source_id,
            substance: values.substance.trim(),
            plan_id: orNull(values.plan_id),
            ...editable,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Замер обновлён" : "Замер внесён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить замер");
      } else {
        toast.error("Не удалось сохранить замер");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyMeasurementFormValues) => {
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
            {isEdit ? "Изменить замер" : "Внести замер"}
          </DialogTitle>
          <DialogDescription>
            Результат замера из протокола лаборатории. Превышение показывается
            сравнением с внесённым нормативом — платформа сама «допустимое»
            значение не назначает.
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
              <Label htmlFor="eco-measure-source">Источник выбросов</Label>
              <select
                id="eco-measure-source"
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
              <Label htmlFor="eco-measure-substance">Вещество</Label>
              <Input
                id="eco-measure-substance"
                placeholder="напр. Азота диоксид"
                disabled={isEdit}
                {...form.register("substance")}
              />
              {fieldError("substance")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-measure-date">Дата замера</Label>
              <Input
                id="eco-measure-date"
                type="date"
                {...form.register("measured_on")}
              />
              {fieldError("measured_on")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-measure-value">Результат, г/с</Label>
              <Input
                id="eco-measure-value"
                inputMode="decimal"
                placeholder="из протокола"
                {...form.register("value_grams_per_second")}
              />
              {fieldError("value_grams_per_second")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Строка плана, протокол и лаборатория
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="eco-measure-plan">Строка плана ПЭК</Label>
                <select
                  id="eco-measure-plan"
                  className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                  disabled={isEdit}
                  title="Пусто — замер вне графика, например по предписанию"
                  {...form.register("plan_id")}
                >
                  <option value="">— Вне графика —</option>
                  {planItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.substance} · {item.periodicity_label}
                    </option>
                  ))}
                </select>
                {fieldError("plan_id")}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="eco-measure-protocol">Протокол</Label>
                  <Input
                    id="eco-measure-protocol"
                    placeholder="номер протокола"
                    {...form.register("protocol_number")}
                  />
                  {fieldError("protocol_number")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-measure-lab">Лаборатория</Label>
                  <Input
                    id="eco-measure-lab"
                    placeholder="кто проводил замер"
                    {...form.register("laboratory")}
                  />
                  {fieldError("laboratory")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-measure-notes">Заметки</Label>
                <Textarea
                  id="eco-measure-notes"
                  rows={3}
                  placeholder="условия замера, особенности"
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
