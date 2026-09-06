import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  MONTH_TITLES,
  WATER_RECORD_BASIS_TITLES,
  ecologyApi,
  type WaterPointDto,
  type WaterRecordDto,
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
  ecologyWaterRecordFormSchema,
  type EcologyWaterRecordFormValues,
} from "@/types/forms/ecologyWater";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyWaterRecordFormValues = {
  point_id: "",
  period_year: String(new Date().getFullYear()),
  period_month: String(new Date().getMonth() + 1),
  volume_cubic_meters: "",
  basis: "meter",
  meter_number: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyWaterRecordFormValues> = {
  point_id: "point_id",
  period_year: "period_year",
  period_month: "period_month",
  volume_cubic_meters: "volume_cubic_meters",
  basis: "basis",
  meter_number: "meter_number",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyWaterRecordFormDialogProps {
  trigger: ReactNode;
  points: WaterPointDto[];
  initialData?: WaterRecordDto;
  onSubmitted?: (record: WaterRecordDto) => void;
}

/**
 * Форма записи учёта водопользования (разд. 55.2, срез-101).
 *
 * Пять полей на первом уровне: точка, год, месяц, объём и основание учёта;
 * номер прибора и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: единица учёта — месяц, и пара «точка + период» уникальна в базе —
 * вторая запись за тот же месяц означает ошибку ввода, сервер отвечает 422
 * словами. Точку и период при правке не меняют: это ключ записи, а не её
 * содержание. Нулевой объём принимается: месяц без водопользования — факт.
 */
export const EcologyWaterRecordFormDialog = ({
  trigger,
  points,
  initialData,
  onSubmitted,
}: EcologyWaterRecordFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyWaterRecordFormValues>({
    resolver: zodResolver(ecologyWaterRecordFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        point_id: initialData.point_id,
        period_year: String(initialData.period_year),
        period_month: String(initialData.period_month),
        volume_cubic_meters: initialData.volume_cubic_meters,
        basis: initialData.basis,
        meter_number: initialData.meter_number ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyWaterRecordFormValues) => {
    const editable = {
      volume_cubic_meters: values.volume_cubic_meters.trim().replace(",", "."),
      basis: values.basis,
      meter_number: orNull(values.meter_number),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateWaterRecord(initialData.id, editable)
        : await ecologyApi.createWaterRecord({
            point_id: values.point_id,
            period_year: Number(values.period_year),
            period_month: Number(values.period_month),
            ...editable,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Запись обновлена" : "Объём записан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить запись");
      } else {
        toast.error("Не удалось сохранить запись");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyWaterRecordFormValues) => {
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
            {isEdit ? "Изменить запись" : "Записать объём"}
          </DialogTitle>
          <DialogDescription>
            Учёт ведётся помесячно: за один месяц у точки одна запись. Чем
            измерен объём — прибором или расчётом — спрашивает надзор, поэтому
            основание обязательно.
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
          <div className="space-y-2">
            <Label htmlFor="eco-record-point">Точка водопользования</Label>
            <select
              id="eco-record-point"
              className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
              disabled={isEdit}
              {...form.register("point_id")}
            >
              <option value="">— Выберите точку —</option>
              {points.map((point) => (
                <option key={point.id} value={point.id}>
                  №{point.point_number} · {point.name}
                </option>
              ))}
            </select>
            {fieldError("point_id")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-record-year">Год</Label>
              <Input
                id="eco-record-year"
                type="number"
                min={2000}
                max={2100}
                inputMode="numeric"
                disabled={isEdit}
                {...form.register("period_year")}
              />
              {fieldError("period_year")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-record-month">Месяц</Label>
              <select
                id="eco-record-month"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("period_month")}
              >
                {Object.entries(MONTH_TITLES).map(([number, title]) => (
                  <option key={number} value={number}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("period_month")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-record-volume">Объём, м³</Label>
              <Input
                id="eco-record-volume"
                inputMode="decimal"
                placeholder="напр. 1250,500"
                {...form.register("volume_cubic_meters")}
              />
              {fieldError("volume_cubic_meters")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-record-basis">Основание учёта</Label>
              <select
                id="eco-record-basis"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("basis")}
              >
                {Object.entries(WATER_RECORD_BASIS_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("basis")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Прибор учёта и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="eco-record-meter">Номер прибора учёта</Label>
                <Input
                  id="eco-record-meter"
                  placeholder="если объём измерен прибором"
                  {...form.register("meter_number")}
                />
                {fieldError("meter_number")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-record-notes">Заметки</Label>
                <Textarea
                  id="eco-record-notes"
                  rows={3}
                  placeholder="методика расчёта, особенности"
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
