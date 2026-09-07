import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  VEHICLE_KIND_TITLES,
  VEHICLE_STATUS_TITLES,
  roadSafetyApi,
  type VehicleDto,
} from "@/api/roadSafety";
import type { Site } from "@/api/sites";
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
  vehicleFormSchema,
  yearToPayload,
  type VehicleFormValues,
} from "@/types/forms/roadSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: VehicleFormValues = {
  plate_number: "",
  brand_model: "",
  kind: "passenger_car",
  status: "in_service",
  inspection_due: "",
  insurance_due: "",
  site_id: "",
  vin: "",
  year_made: "",
  license_number: "",
  license_due: "",
  tachograph_installed: false,
  tachograph_due: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof VehicleFormValues> = {
  plate_number: "plate_number",
  brand_model: "brand_model",
  kind: "kind",
  status: "status",
  inspection_due: "inspection_due",
  insurance_due: "insurance_due",
  site_id: "site_id",
  vin: "vin",
  year_made: "year_made",
  license_number: "license_number",
  license_due: "license_due",
  tachograph_due: "tachograph_due",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface VehicleFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: VehicleDto;
  onSubmitted?: (vehicle: VehicleDto) => void;
}

/**
 * Форма транспортного средства (разд. 56.2, срез-107).
 *
 * Шесть полей на первом уровне: госномер, марка и модель, вид, состояние и два
 * главных срока — диагностической карты и полиса; VIN, год, площадка,
 * лицензия, тахограф и заметки — под «Дополнительно» (ТЗ разд. 59.3).
 *
 * ГРАНИЦЫ: платформа не решает, нужна ли ТС лицензия и обязателен ли тахограф
 * (следует из вида перевозок, массы и категории). Пустой срок здесь означает
 * «сведения не внесены», а НЕ «бессрочно» — у диагностической карты и полиса
 * бессрочности не бывает. Списание — состояние, а не удаление: история
 * остаётся, а просрочки считаются только по эксплуатируемым.
 */
export const VehicleFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: VehicleFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<VehicleFormValues>({
    resolver: zodResolver(vehicleFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        plate_number: initialData.plate_number,
        brand_model: initialData.brand_model,
        kind: initialData.kind,
        status: initialData.status,
        inspection_due: initialData.inspection_due ?? "",
        insurance_due: initialData.insurance_due ?? "",
        site_id: initialData.site_id ?? "",
        vin: initialData.vin ?? "",
        year_made:
          initialData.year_made != null ? String(initialData.year_made) : "",
        license_number: initialData.license_number ?? "",
        license_due: initialData.license_due ?? "",
        tachograph_installed: initialData.tachograph_installed,
        tachograph_due: initialData.tachograph_due ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: VehicleFormValues) => {
    const body = {
      plate_number: values.plate_number.trim(),
      brand_model: values.brand_model.trim(),
      kind: values.kind,
      status: values.status,
      vin: orNull(values.vin),
      year_made: yearToPayload(values.year_made),
      site_id: orNull(values.site_id),
      inspection_due: orNull(values.inspection_due),
      insurance_due: orNull(values.insurance_due),
      license_number: orNull(values.license_number),
      license_due: orNull(values.license_due),
      tachograph_installed: Boolean(values.tachograph_installed),
      tachograph_due: orNull(values.tachograph_due),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await roadSafetyApi.updateVehicle(initialData.id, body)
        : await roadSafetyApi.createVehicle(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "ТС обновлено" : "ТС заведено");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить ТС");
      } else {
        toast.error("Не удалось сохранить ТС");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof VehicleFormValues) => {
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
          <DialogTitle>{isEdit ? "Изменить ТС" : "Завести ТС"}</DialogTitle>
          <DialogDescription>
            Сведения из документов на машину. Пустой срок означает «сведения не
            внесены», а не «бессрочно»: у диагностической карты и полиса
            бессрочности не бывает. Нужны ли лицензия и тахограф, определяет вид
            перевозок — платформа этого не решает.
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
              <Label htmlFor="veh-plate">Госномер</Label>
              <Input
                id="veh-plate"
                placeholder="А123ВС777"
                {...form.register("plate_number")}
              />
              {fieldError("plate_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="veh-brand">Марка и модель</Label>
              <Input
                id="veh-brand"
                placeholder="ГАЗ-3302"
                {...form.register("brand_model")}
              />
              {fieldError("brand_model")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="veh-kind">Вид ТС</Label>
              <select
                id="veh-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(VEHICLE_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="veh-status">Состояние</Label>
              <select
                id="veh-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(VEHICLE_STATUS_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("status")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="veh-inspection">Диагностическая карта до</Label>
              <Input
                id="veh-inspection"
                type="date"
                {...form.register("inspection_due")}
              />
              {fieldError("inspection_due")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="veh-insurance">Полис ОСАГО до</Label>
              <Input
                id="veh-insurance"
                type="date"
                {...form.register("insurance_due")}
              />
              {fieldError("insurance_due")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              VIN, площадка, лицензия и тахограф
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="veh-vin">VIN</Label>
                  <Input id="veh-vin" {...form.register("vin")} />
                  {fieldError("vin")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="veh-year">Год выпуска</Label>
                  <Input
                    id="veh-year"
                    inputMode="numeric"
                    {...form.register("year_made")}
                  />
                  {fieldError("year_made")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="veh-site">Площадка</Label>
                  <select
                    id="veh-site"
                    className="h-10 w-full rounded-md border px-3"
                    {...form.register("site_id")}
                  >
                    <option value="">— Не привязано —</option>
                    {sites.map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.name}
                      </option>
                    ))}
                  </select>
                  {fieldError("site_id")}
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="veh-license">Номер лицензии</Label>
                  <Input
                    id="veh-license"
                    {...form.register("license_number")}
                  />
                  {fieldError("license_number")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="veh-license-due">Лицензия до</Label>
                  <Input
                    id="veh-license-due"
                    type="date"
                    {...form.register("license_due")}
                  />
                  {fieldError("license_due")}
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="flex items-center gap-2 pt-6">
                  <input
                    id="veh-tacho"
                    type="checkbox"
                    className="h-4 w-4"
                    {...form.register("tachograph_installed")}
                  />
                  <Label htmlFor="veh-tacho">Тахограф установлен</Label>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="veh-tacho-due">Поверка тахографа до</Label>
                  <Input
                    id="veh-tacho-due"
                    type="date"
                    {...form.register("tachograph_due")}
                  />
                  {fieldError("tachograph_due")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="veh-notes">Заметки</Label>
                <Textarea
                  id="veh-notes"
                  rows={3}
                  placeholder="особенности эксплуатации"
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
