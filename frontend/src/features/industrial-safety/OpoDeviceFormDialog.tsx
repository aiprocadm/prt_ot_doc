import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  OPO_DEVICE_KIND_TITLES,
  OPO_DEVICE_STATUS_TITLES,
  industrialSafetyApi,
  type HazardousFacilityDto,
  type TechnicalDeviceDto,
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
  opoDeviceFormSchema,
  type OpoDeviceFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: OpoDeviceFormValues = {
  facility_id: "",
  kind: "pressure_vessel",
  name: "",
  serial_number: "",
  status: "in_operation",
  lifetime_until: "",
  commissioned_on: "",
  epb_conclusion_number: "",
  epb_registered_on: "",
  epb_valid_until: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof OpoDeviceFormValues> = {
  facility_id: "facility_id",
  kind: "kind",
  name: "name",
  serial_number: "serial_number",
  status: "status",
  lifetime_until: "lifetime_until",
  commissioned_on: "commissioned_on",
  epb_conclusion_number: "epb_conclusion_number",
  epb_registered_on: "epb_registered_on",
  epb_valid_until: "epb_valid_until",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface OpoDeviceFormDialogProps {
  trigger: ReactNode;
  facilities: HazardousFacilityDto[];
  initialData?: TechnicalDeviceDto;
  onSubmitted?: (device: TechnicalDeviceDto) => void;
}

/**
 * Форма технического устройства на ОПО (разд. 54.2, срез-105).
 *
 * Шесть полей на первом уровне: объект, вид, наименование, заводской номер,
 * состояние и срок службы; ввод в эксплуатацию и реквизиты заключения ЭПБ —
 * под «Дополнительно».
 *
 * ГРАНИЦЫ: платформа НЕ решает, нужна ли устройству экспертиза (зависит от
 * типа, документации и норм ФНП) — поля заключения необязательны, а
 * «заключения нет» это отдельное состояние, не просрочка. Вывод из
 * эксплуатации — состояние, а не удаление: списанное уходит из сводки, но
 * история остаётся.
 */
export const OpoDeviceFormDialog = ({
  trigger,
  facilities,
  initialData,
  onSubmitted,
}: OpoDeviceFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<OpoDeviceFormValues>({
    resolver: zodResolver(opoDeviceFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        facility_id: initialData.facility_id,
        kind: initialData.kind,
        name: initialData.name,
        serial_number: initialData.serial_number ?? "",
        status: initialData.status,
        lifetime_until: initialData.lifetime_until ?? "",
        commissioned_on: initialData.commissioned_on ?? "",
        epb_conclusion_number: initialData.epb_conclusion_number ?? "",
        epb_registered_on: initialData.epb_registered_on ?? "",
        epb_valid_until: initialData.epb_valid_until ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: OpoDeviceFormValues) => {
    const body = {
      facility_id: values.facility_id,
      kind: values.kind,
      name: values.name.trim(),
      serial_number: orNull(values.serial_number),
      status: values.status,
      lifetime_until: orNull(values.lifetime_until),
      commissioned_on: orNull(values.commissioned_on),
      epb_conclusion_number: orNull(values.epb_conclusion_number),
      epb_registered_on: orNull(values.epb_registered_on),
      epb_valid_until: orNull(values.epb_valid_until),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await industrialSafetyApi.updateDevice(initialData.id, body)
        : await industrialSafetyApi.createDevice(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Устройство обновлено" : "Устройство заведено");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить устройство");
      } else {
        toast.error("Не удалось сохранить устройство");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof OpoDeviceFormValues) => {
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
            {isEdit ? "Изменить устройство" : "Завести устройство"}
          </DialogTitle>
          <DialogDescription>
            Устройство учитывается на зарегистрированном объекте. Нужна ли
            экспертиза и когда — определяют тип устройства и нормы ФНП;
            платформа этого не решает, а «заключения нет» показывает отдельно от
            просрочки.
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
              <Label htmlFor="opo-device-facility">Объект (ОПО)</Label>
              <select
                id="opo-device-facility"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("facility_id")}
              >
                <option value="">— Выберите объект —</option>
                {facilities.map((facility) => (
                  <option key={facility.id} value={facility.id}>
                    {facility.name}
                  </option>
                ))}
              </select>
              {fieldError("facility_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-device-kind">Вид устройства</Label>
              <select
                id="opo-device-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(OPO_DEVICE_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="opo-device-name">Устройство</Label>
            <Input
              id="opo-device-name"
              placeholder="напр. Сосуд В-1 котельной"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="opo-device-serial">Заводской номер</Label>
              <Input
                id="opo-device-serial"
                placeholder="по паспорту"
                {...form.register("serial_number")}
              />
              {fieldError("serial_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-device-status">Состояние</Label>
              <select
                id="opo-device-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(OPO_DEVICE_STATUS_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("status")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-device-lifetime">Срок службы до</Label>
              <Input
                id="opo-device-lifetime"
                type="date"
                title="Из паспорта устройства; пусто — не внесён"
                {...form.register("lifetime_until")}
              />
              {fieldError("lifetime_until")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Ввод в эксплуатацию и заключение экспертизы
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="opo-device-commissioned">
                    Введено в эксплуатацию
                  </Label>
                  <Input
                    id="opo-device-commissioned"
                    type="date"
                    {...form.register("commissioned_on")}
                  />
                  {fieldError("commissioned_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="opo-device-epb-number">
                    Номер заключения ЭПБ
                  </Label>
                  <Input
                    id="opo-device-epb-number"
                    placeholder="как в реестре Ростехнадзора"
                    {...form.register("epb_conclusion_number")}
                  />
                  {fieldError("epb_conclusion_number")}
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="opo-device-epb-registered">
                    Заключение зарегистрировано
                  </Label>
                  <Input
                    id="opo-device-epb-registered"
                    type="date"
                    {...form.register("epb_registered_on")}
                  />
                  {fieldError("epb_registered_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="opo-device-epb-valid">
                    Заключение действует до
                  </Label>
                  <Input
                    id="opo-device-epb-valid"
                    type="date"
                    {...form.register("epb_valid_until")}
                  />
                  {fieldError("epb_valid_until")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="opo-device-notes">Заметки</Label>
                <Textarea
                  id="opo-device-notes"
                  rows={3}
                  placeholder="условия эксплуатации, особенности"
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
