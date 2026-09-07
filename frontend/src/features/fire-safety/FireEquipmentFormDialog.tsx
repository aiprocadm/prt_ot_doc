import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FIRE_EQUIPMENT_TITLES,
  fireSafetyApi,
  type FireEquipmentDto,
} from "@/api/fireSafety";
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
import {
  fireEquipmentFormSchema,
  type FireEquipmentFormValues,
} from "@/types/forms/fireSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: FireEquipmentFormValues = {
  kind: "extinguisher",
  label: "",
  site_id: "",
  location: "",
  recharge_due: "",
  inspection_due: "",
};

const API_FIELD_MAP: Record<string, keyof FireEquipmentFormValues> = {
  kind: "kind",
  label: "label",
  site_id: "site_id",
  location: "location",
  recharge_due: "recharge_due",
  inspection_due: "inspection_due",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface FireEquipmentFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: FireEquipmentDto;
  onSubmitted?: (unit: FireEquipmentDto) => void;
}

/**
 * Форма средства защиты или системы ПБ (разд. 54.1, срез-103).
 *
 * До неё ручки `POST/PATCH /fire-safety/equipment` (срез-4) работали только
 * через API: экран звал «внесите огнетушители, краны, щиты и системы», а
 * внести их было негде. Шесть полей на первом уровне: вид, наименование,
 * площадка, место и два срока — перезарядки и поверки/ТО.
 *
 * ГРАНИЦА: платформа не решает, какой срок средству нужен (у огнетушителя это
 * перезарядка, у крана — поверка, у лестницы — испытание), и не назначает его
 * сама. Пустой срок означает «не применимо», а не «просрочено». Состояние
 * средства формой не меняется: закрытого словаря состояний на сервере нет, а
 * свободная строка превратила бы реестр в «как записали».
 */
export const FireEquipmentFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: FireEquipmentFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<FireEquipmentFormValues>({
    resolver: zodResolver(fireEquipmentFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        label: initialData.label,
        site_id: initialData.site_id ?? "",
        location: initialData.location ?? "",
        recharge_due: initialData.recharge_due ?? "",
        inspection_due: initialData.inspection_due ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: FireEquipmentFormValues) => {
    const body = {
      kind: values.kind,
      label: values.label.trim(),
      site_id: orNull(values.site_id),
      location: orNull(values.location),
      recharge_due: orNull(values.recharge_due),
      inspection_due: orNull(values.inspection_due),
    };
    try {
      const result = initialData
        ? await fireSafetyApi.updateEquipment(initialData.id, body)
        : await fireSafetyApi.createEquipment(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Средство обновлено" : "Средство заведено");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить средство");
      } else {
        toast.error("Не удалось сохранить средство");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof FireEquipmentFormValues) => {
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
            {isEdit ? "Изменить средство" : "Завести средство"}
          </DialogTitle>
          <DialogDescription>
            Сроки перезарядки и поверки вносятся по паспорту средства и
            регламенту: платформа их не назначает. Пустой срок означает «не
            применимо», а не «просрочено».
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
              <Label htmlFor="fire-unit-kind">Вид средства</Label>
              <select
                id="fire-unit-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(FIRE_EQUIPMENT_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="fire-unit-label">Наименование или номер</Label>
              <Input
                id="fire-unit-label"
                placeholder="напр. ОП-5 №14"
                {...form.register("label")}
              />
              {fieldError("label")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="fire-unit-site">Площадка</Label>
              <select
                id="fire-unit-site"
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
            <div className="space-y-2">
              <Label htmlFor="fire-unit-location">Место установки</Label>
              <Input
                id="fire-unit-location"
                placeholder="цех, этаж, помещение"
                {...form.register("location")}
              />
              {fieldError("location")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="fire-unit-recharge">Перезарядка до</Label>
              <Input
                id="fire-unit-recharge"
                type="date"
                title="Пусто — к этому средству не применимо"
                {...form.register("recharge_due")}
              />
              {fieldError("recharge_due")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="fire-unit-inspection">Поверка / ТО до</Label>
              <Input
                id="fire-unit-inspection"
                type="date"
                title="Пусто — к этому средству не применимо"
                {...form.register("inspection_due")}
              />
              {fieldError("inspection_due")}
            </div>
          </div>
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
