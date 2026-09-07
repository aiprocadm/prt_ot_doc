import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  ACCIDENT_FAULT_TITLES,
  ACCIDENT_KIND_TITLES,
  roadSafetyApi,
  type DriverDto,
  type RoadAccidentDto,
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
  accidentFormSchema,
  countToPayload,
  isoToLocalDateTime,
  localDateTimeToPayload,
  type AccidentFormValues,
} from "@/types/forms/roadSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: AccidentFormValues = {
  occurred_at: "",
  place: "",
  vehicle_id: "",
  kind: "collision",
  driver_id: "",
  fault: "not_established",
  injured_count: "",
  fatalities_count: "",
  gibdd_reference: "",
  description: "",
};

const API_FIELD_MAP: Record<string, keyof AccidentFormValues> = {
  occurred_at: "occurred_at",
  place: "place",
  vehicle_id: "vehicle_id",
  kind: "kind",
  driver_id: "driver_id",
  fault: "fault",
  injured_count: "injured_count",
  fatalities_count: "fatalities_count",
  gibdd_reference: "gibdd_reference",
  description: "description",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface AccidentFormDialogProps {
  trigger: ReactNode;
  vehicles: VehicleDto[];
  drivers: DriverDto[];
  initialData?: RoadAccidentDto;
  onSubmitted?: (accident: RoadAccidentDto) => void;
}

/**
 * Форма регистрации ДТП (разд. 56.2, срез-108).
 *
 * Пять полей на первом уровне: дата и время, место, машина, вид и вина;
 * водитель, число пострадавших и погибших, номер материала ГИБДД и описание —
 * под «Дополнительно».
 *
 * ГРАНИЦЫ: вину устанавливают ГИБДД и суд — по умолчанию «не установлена», и
 * платформа её не выводит; тяжесть последствий считает сервер из чисел людей,
 * поля «тяжесть» в форме нет. Водитель необязателен: в стоящую машину въезжают
 * и без него. Машину при правке не меняют — это другое ДТП.
 */
export const AccidentFormDialog = ({
  trigger,
  vehicles,
  drivers,
  initialData,
  onSubmitted,
}: AccidentFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<AccidentFormValues>({
    resolver: zodResolver(accidentFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        occurred_at: isoToLocalDateTime(initialData.occurred_at),
        place: initialData.place,
        vehicle_id: initialData.vehicle_id,
        kind: initialData.kind,
        driver_id: initialData.driver_id ?? "",
        fault: initialData.fault,
        injured_count: String(initialData.injured_count),
        fatalities_count: String(initialData.fatalities_count),
        gibdd_reference: initialData.gibdd_reference ?? "",
        description: initialData.description ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: AccidentFormValues) => {
    const common = {
      occurred_at: localDateTimeToPayload(values.occurred_at),
      place: values.place.trim(),
      driver_id: orNull(values.driver_id),
      kind: values.kind,
      injured_count: countToPayload(values.injured_count),
      fatalities_count: countToPayload(values.fatalities_count),
      fault: values.fault,
      gibdd_reference: orNull(values.gibdd_reference),
      description: orNull(values.description),
    };
    try {
      const result = initialData
        ? await roadSafetyApi.updateAccident(initialData.id, common)
        : await roadSafetyApi.createAccident({
            vehicle_id: values.vehicle_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "ДТП обновлено" : "ДТП зарегистрировано");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить ДТП");
      } else {
        toast.error("Не удалось сохранить ДТП");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof AccidentFormValues) => {
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
            {isEdit ? "Изменить запись о ДТП" : "Зарегистрировать ДТП"}
          </DialogTitle>
          <DialogDescription>
            Вину устанавливают ГИБДД и суд — по умолчанию «не установлена»;
            платформа её не выводит. Тяжесть последствий считается из числа
            пострадавших и погибших.
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
              <Label htmlFor="acc-occurred">Дата и время</Label>
              <Input
                id="acc-occurred"
                type="datetime-local"
                {...form.register("occurred_at")}
              />
              {fieldError("occurred_at")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="acc-kind">Вид ДТП</Label>
              <select
                id="acc-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(ACCIDENT_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="acc-place">Место</Label>
            <Input
              id="acc-place"
              placeholder="адрес или километр дороги"
              {...form.register("place")}
            />
            {fieldError("place")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="acc-vehicle">Машина</Label>
              <select
                id="acc-vehicle"
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
              <Label htmlFor="acc-fault">Вина</Label>
              <select
                id="acc-fault"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("fault")}
              >
                {Object.entries(ACCIDENT_FAULT_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("fault")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Водитель, последствия и материал ГИБДД
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="acc-driver">Водитель</Label>
                <select
                  id="acc-driver"
                  className="h-10 w-full rounded-md border px-3"
                  title="Пусто — за рулём никого не было (наезд на стоящую машину)"
                  {...form.register("driver_id")}
                >
                  <option value="">— За рулём никого не было —</option>
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
                  <Label htmlFor="acc-injured">Пострадавших</Label>
                  <Input
                    id="acc-injured"
                    type="number"
                    min={0}
                    inputMode="numeric"
                    {...form.register("injured_count")}
                  />
                  {fieldError("injured_count")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="acc-fatal">Погибших</Label>
                  <Input
                    id="acc-fatal"
                    type="number"
                    min={0}
                    inputMode="numeric"
                    {...form.register("fatalities_count")}
                  />
                  {fieldError("fatalities_count")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="acc-gibdd">Материал ГИБДД</Label>
                  <Input
                    id="acc-gibdd"
                    placeholder="номер"
                    {...form.register("gibdd_reference")}
                  />
                  {fieldError("gibdd_reference")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="acc-description">Обстоятельства</Label>
                <Textarea
                  id="acc-description"
                  rows={3}
                  placeholder="что произошло по документам"
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
