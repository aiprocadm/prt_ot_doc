import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  VIOLATION_SOURCE_TITLES,
  roadSafetyApi,
  type DriverDto,
  type TrafficViolationDto,
  type VehicleDto,
} from "@/api/roadSafety";
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
  fineToPayload,
  isoToLocalDateTime,
  localDateTimeToPayload,
  violationFormSchema,
  type ViolationFormValues,
} from "@/types/forms/roadSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: ViolationFormValues = {
  vehicle_id: "",
  occurred_at: "",
  source: "camera",
  article: "",
  fine_amount: "",
  driver_id: "",
  resolution_number: "",
  place: "",
  fine_paid_on: "",
  description: "",
};

const API_FIELD_MAP: Record<string, keyof ViolationFormValues> = {
  vehicle_id: "vehicle_id",
  occurred_at: "occurred_at",
  source: "source",
  article: "article",
  fine_amount: "fine_amount",
  driver_id: "driver_id",
  resolution_number: "resolution_number",
  place: "place",
  fine_paid_on: "fine_paid_on",
  description: "description",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface ViolationFormDialogProps {
  trigger: ReactNode;
  vehicles: VehicleDto[];
  drivers: DriverDto[];
  initialData?: TrafficViolationDto;
  onSubmitted?: (violation: TrafficViolationDto) => void;
}

/**
 * Форма нарушения ПДД (разд. 56.2, срез-108).
 *
 * Пять полей на первом уровне: машина, дата и время, способ выявления, статья
 * и сумма штрафа; водитель, номер постановления, место, дата оплаты и описание
 * — под «Дополнительно».
 *
 * ГРАНИЦЫ: водитель НЕОБЯЗАТЕЛЕН — камера фиксирует госномер, а не человека;
 * «водитель не установлен» это факт, а не незаполненное поле. Пустая сумма
 * означает «штраф не наложен», а не «сумма неизвестна». Статья КоАП —
 * свободная строка: закрытый словарь отстал бы от поправок. Машину при правке
 * не меняют — это другое нарушение.
 */
export const ViolationFormDialog = ({
  trigger,
  vehicles,
  drivers,
  initialData,
  onSubmitted,
}: ViolationFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<ViolationFormValues>({
    resolver: zodResolver(violationFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        vehicle_id: initialData.vehicle_id,
        occurred_at: isoToLocalDateTime(initialData.occurred_at),
        source: initialData.source,
        article: initialData.article ?? "",
        fine_amount: initialData.fine_amount ?? "",
        driver_id: initialData.driver_id ?? "",
        resolution_number: initialData.resolution_number ?? "",
        place: initialData.place ?? "",
        fine_paid_on: initialData.fine_paid_on ?? "",
        description: initialData.description ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: ViolationFormValues) => {
    const common = {
      occurred_at: localDateTimeToPayload(values.occurred_at),
      source: values.source,
      article: orNull(values.article),
      fine_amount: fineToPayload(values.fine_amount),
      driver_id: orNull(values.driver_id),
      resolution_number: orNull(values.resolution_number),
      place: orNull(values.place),
      fine_paid_on: orNull(values.fine_paid_on),
      description: orNull(values.description),
    };
    try {
      const result = initialData
        ? await roadSafetyApi.updateViolation(initialData.id, common)
        : await roadSafetyApi.createViolation({
            vehicle_id: values.vehicle_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Нарушение обновлено" : "Нарушение внесено");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить нарушение");
      } else {
        toast.error("Не удалось сохранить нарушение");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof ViolationFormValues) => {
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
            {isEdit ? "Изменить нарушение" : "Внести нарушение"}
          </DialogTitle>
          <DialogDescription>
            Камера фиксирует госномер, а не человека: водителя можно не
            указывать — «не установлен» это факт. Пустая сумма означает, что
            штраф не наложен, а не что сумма неизвестна.
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
              <Label htmlFor="vio-vehicle">Машина</Label>
              <select
                id="vio-vehicle"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("vehicle_id")}
              >
                <option value="">— Выберите машину —</option>
                {vehicles.map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {vehicle.plate_number} · {vehicle.brand_model}
                  </option>
                ))}
              </select>
              {fieldError("vehicle_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="vio-occurred">Дата и время</Label>
              <Input
                id="vio-occurred"
                type="datetime-local"
                {...form.register("occurred_at")}
              />
              {fieldError("occurred_at")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="vio-source">Способ выявления</Label>
              <select
                id="vio-source"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("source")}
              >
                {Object.entries(VIOLATION_SOURCE_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("source")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="vio-article">Статья КоАП</Label>
              <Input
                id="vio-article"
                placeholder="напр. 12.9 ч.2"
                {...form.register("article")}
              />
              {fieldError("article")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="vio-fine">Штраф, ₽</Label>
              <Input
                id="vio-fine"
                inputMode="decimal"
                placeholder="пусто — не наложен"
                {...form.register("fine_amount")}
              />
              {fieldError("fine_amount")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Водитель, постановление, место и оплата
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="vio-driver">Водитель</Label>
                <select
                  id="vio-driver"
                  className="h-10 w-full rounded-md border px-3"
                  title="Пусто — водитель не установлен: камера снимает машину"
                  {...form.register("driver_id")}
                >
                  <option value="">— Не установлен —</option>
                  {drivers.map((driver) => (
                    <option key={driver.id} value={driver.id}>
                      {driver.person_name}
                    </option>
                  ))}
                </select>
                {fieldError("driver_id")}
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="vio-resolution">Постановление</Label>
                  <Input
                    id="vio-resolution"
                    placeholder="номер"
                    {...form.register("resolution_number")}
                  />
                  {fieldError("resolution_number")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vio-place">Место</Label>
                  <Input id="vio-place" {...form.register("place")} />
                  {fieldError("place")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vio-paid">Оплачен</Label>
                  <Input
                    id="vio-paid"
                    type="date"
                    {...form.register("fine_paid_on")}
                  />
                  {fieldError("fine_paid_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="vio-description">Описание</Label>
                <Textarea
                  id="vio-description"
                  rows={3}
                  placeholder="обстоятельства, меры к водителю"
                  {...form.register("description")}
                />
                {fieldError("description")}
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
