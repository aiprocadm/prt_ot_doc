import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  WAYBILL_MARK_TITLES,
  WAYBILL_STATUS_TITLES,
  roadSafetyApi,
  type DriverDto,
  type VehicleDto,
  type WaybillDto,
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
  isoToLocalDateTime,
  localDateTimeToPayload,
  waybillFormSchema,
  type WaybillFormValues,
} from "@/types/forms/roadSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: WaybillFormValues = {
  number: "",
  vehicle_id: "",
  driver_id: "",
  issued_on: "",
  status: "issued",
  pre_trip_medical: "not_recorded",
  pre_trip_technical: "not_recorded",
  post_trip_medical: "not_recorded",
  departure_at: "",
  return_at: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof WaybillFormValues> = {
  number: "number",
  vehicle_id: "vehicle_id",
  driver_id: "driver_id",
  issued_on: "issued_on",
  status: "status",
  pre_trip_medical: "pre_trip_medical",
  pre_trip_technical: "pre_trip_technical",
  post_trip_medical: "post_trip_medical",
  departure_at: "departure_at",
  return_at: "return_at",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? localDateTimeToPayload(value.trim()) : null;

interface WaybillFormDialogProps {
  trigger: ReactNode;
  vehicles: VehicleDto[];
  drivers: DriverDto[];
  initialData?: WaybillDto;
  onSubmitted?: (waybill: WaybillDto) => void;
}

/**
 * Форма путевого листа (разд. 56.2, срез-108).
 *
 * Пять полей на первом уровне: номер, машина, водитель, дата выдачи и
 * состояние; отметки контроля, время рейса и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: отметки по умолчанию «сведения не внесены» — свежий лист
 * выписывается ДО осмотра, и это законное состояние, а не нарушение. Вердикт о
 * выпуске считает сервер по двум обязательным отметкам; форма его не выводит и
 * «законен ли выпуск» не решает. Машину и водителя при правке не меняют — это
 * другой рейс (ручка PATCH их не принимает).
 */
export const WaybillFormDialog = ({
  trigger,
  vehicles,
  drivers,
  initialData,
  onSubmitted,
}: WaybillFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<WaybillFormValues>({
    resolver: zodResolver(waybillFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        number: initialData.number,
        vehicle_id: initialData.vehicle_id,
        driver_id: initialData.driver_id,
        issued_on: initialData.issued_on,
        status: initialData.status,
        pre_trip_medical: initialData.pre_trip_medical,
        pre_trip_technical: initialData.pre_trip_technical,
        post_trip_medical: initialData.post_trip_medical,
        departure_at: isoToLocalDateTime(initialData.departure_at),
        return_at: isoToLocalDateTime(initialData.return_at),
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: WaybillFormValues) => {
    const common = {
      number: values.number.trim(),
      issued_on: values.issued_on,
      status: values.status,
      pre_trip_medical: values.pre_trip_medical,
      pre_trip_technical: values.pre_trip_technical,
      post_trip_medical: values.post_trip_medical,
      departure_at: orNull(values.departure_at),
      return_at: orNull(values.return_at),
      notes: values.notes?.trim() ? values.notes.trim() : null,
    };
    try {
      const result = initialData
        ? await roadSafetyApi.updateWaybill(initialData.id, common)
        : await roadSafetyApi.createWaybill({
            vehicle_id: values.vehicle_id,
            driver_id: values.driver_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Лист обновлён" : "Лист выписан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить путевой лист");
      } else {
        toast.error("Не удалось сохранить путевой лист");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof WaybillFormValues) => {
    const message = form.formState.errors[name]?.message;
    return message ? (
      <p className="text-xs text-destructive">{message}</p>
    ) : null;
  };

  const markField = (
    name: "pre_trip_medical" | "pre_trip_technical" | "post_trip_medical",
    id: string,
    label: string,
  ) => (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        className="h-10 w-full rounded-md border px-3"
        {...form.register(name)}
      >
        {Object.entries(WAYBILL_MARK_TITLES).map(([code, title]) => (
          <option key={code} value={code}>
            {title}
          </option>
        ))}
      </select>
      {fieldError(name)}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Изменить путевой лист" : "Выписать путевой лист"}
          </DialogTitle>
          <DialogDescription>
            Отметки контроля можно не заполнять: свежий лист выписывается до
            осмотра, и «сведения не внесены» — законное состояние, а не
            нарушение. Вердикт о выпуске считает система по двум обязательным
            отметкам.
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
              <Label htmlFor="wb-number">Номер листа</Label>
              <Input
                id="wb-number"
                placeholder="напр. 000123"
                {...form.register("number")}
              />
              {fieldError("number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="wb-issued">Выдан</Label>
              <Input
                id="wb-issued"
                type="date"
                {...form.register("issued_on")}
              />
              {fieldError("issued_on")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="wb-vehicle">Машина</Label>
              <select
                id="wb-vehicle"
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
              <Label htmlFor="wb-driver">Водитель</Label>
              <select
                id="wb-driver"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("driver_id")}
              >
                <option value="">— Выберите водителя —</option>
                {drivers.map((driver) => (
                  <option key={driver.id} value={driver.id}>
                    {driver.person_name}
                  </option>
                ))}
              </select>
              {fieldError("driver_id")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="wb-status">Состояние листа</Label>
            <select
              id="wb-status"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("status")}
            >
              {Object.entries(WAYBILL_STATUS_TITLES).map(([code, title]) => (
                <option key={code} value={code}>
                  {title}
                </option>
              ))}
            </select>
            {fieldError("status")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Отметки контроля, время рейса и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                {markField(
                  "pre_trip_medical",
                  "wb-pre-med",
                  "Предрейсовый медосмотр",
                )}
                {markField(
                  "pre_trip_technical",
                  "wb-pre-tech",
                  "Предрейсовый техконтроль",
                )}
                {markField(
                  "post_trip_medical",
                  "wb-post-med",
                  "Послерейсовый медосмотр",
                )}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="wb-departure">Выезд</Label>
                  <Input
                    id="wb-departure"
                    type="datetime-local"
                    {...form.register("departure_at")}
                  />
                  {fieldError("departure_at")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wb-return">Возвращение</Label>
                  <Input
                    id="wb-return"
                    type="datetime-local"
                    {...form.register("return_at")}
                  />
                  {fieldError("return_at")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="wb-notes">Заметки</Label>
                <Textarea
                  id="wb-notes"
                  rows={3}
                  placeholder="маршрут, задание"
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
