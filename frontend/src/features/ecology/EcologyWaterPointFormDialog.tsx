import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  WATER_POINT_KIND_TITLES,
  ecologyApi,
  type EnvironmentalFacilityDto,
  type WaterPointDto,
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
  ecologyWaterPointFormSchema,
  type EcologyWaterPointFormValues,
} from "@/types/forms/ecologyWater";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyWaterPointFormValues = {
  facility_id: "",
  point_number: "",
  name: "",
  kind: "intake",
  annual_limit_cubic_meters: "",
  permit_valid_until: "",
  water_body: "",
  permit_number: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyWaterPointFormValues> = {
  facility_id: "facility_id",
  point_number: "point_number",
  name: "name",
  kind: "kind",
  annual_limit_cubic_meters: "annual_limit_cubic_meters",
  permit_valid_until: "permit_valid_until",
  water_body: "water_body",
  permit_number: "permit_number",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

const numberOrNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim().replace(",", ".") : null;

interface EcologyWaterPointFormDialogProps {
  trigger: ReactNode;
  facilities: EnvironmentalFacilityDto[];
  initialData?: WaterPointDto;
  onSubmitted?: (point: WaterPointDto) => void;
}

/**
 * Форма точки водопользования (разд. 55.2, срез-101).
 *
 * Шесть полей на первом уровне: объект НВОС, номер, название, вид, годовой
 * лимит и срок разрешения; водный объект, номер разрешения и заметки — под
 * «Дополнительно».
 *
 * ГРАНИЦЫ: платформа не решает, нужно ли точке разрешение (забор из городского
 * водопровода идёт по договору без срока), поэтому пустой срок — не просрочка,
 * а пустой лимит означает «не установлен». Объект НВОС при правке заперт:
 * ручка PATCH его не принимает.
 */
export const EcologyWaterPointFormDialog = ({
  trigger,
  facilities,
  initialData,
  onSubmitted,
}: EcologyWaterPointFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyWaterPointFormValues>({
    resolver: zodResolver(ecologyWaterPointFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        facility_id: initialData.facility_id,
        point_number: initialData.point_number,
        name: initialData.name,
        kind: initialData.kind,
        annual_limit_cubic_meters: initialData.annual_limit_cubic_meters ?? "",
        permit_valid_until: initialData.permit_valid_until ?? "",
        water_body: initialData.water_body ?? "",
        permit_number: initialData.permit_number ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyWaterPointFormValues) => {
    const editable = {
      point_number: values.point_number.trim(),
      name: values.name.trim(),
      kind: values.kind,
      water_body: orNull(values.water_body),
      permit_number: orNull(values.permit_number),
      permit_valid_until: orNull(values.permit_valid_until),
      annual_limit_cubic_meters: numberOrNull(values.annual_limit_cubic_meters),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateWaterPoint(initialData.id, editable)
        : await ecologyApi.createWaterPoint({
            facility_id: values.facility_id,
            ...editable,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Точка обновлена" : "Точка заведена");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить точку");
      } else {
        toast.error("Не удалось сохранить точку");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyWaterPointFormValues) => {
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
            {isEdit ? "Изменить точку" : "Завести точку водопользования"}
          </DialogTitle>
          <DialogDescription>
            Забор и сброс — разные точки: их объёмы не складываются. Пустой срок
            разрешения не считается просрочкой: забор из городского водопровода
            идёт по договору без срока.
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
              <Label htmlFor="eco-water-facility">Объект НВОС</Label>
              <select
                id="eco-water-facility"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
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
              <Label htmlFor="eco-water-kind">Вид точки</Label>
              <select
                id="eco-water-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(WATER_POINT_KIND_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("kind")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-water-number">Номер точки</Label>
              <Input
                id="eco-water-number"
                placeholder="напр. В-1"
                {...form.register("point_number")}
              />
              {fieldError("point_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-water-name">Точка</Label>
              <Input
                id="eco-water-name"
                placeholder="напр. Скважина №1"
                {...form.register("name")}
              />
              {fieldError("name")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-water-limit">Годовой лимит, м³</Label>
              <Input
                id="eco-water-limit"
                inputMode="decimal"
                placeholder="пусто — не установлен"
                {...form.register("annual_limit_cubic_meters")}
              />
              {fieldError("annual_limit_cubic_meters")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-water-valid">Разрешение действует до</Label>
              <Input
                id="eco-water-valid"
                type="date"
                title="Пусто — договор без срока, это не просрочка"
                {...form.register("permit_valid_until")}
              />
              {fieldError("permit_valid_until")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Водный объект, разрешение и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="eco-water-body">Водный объект</Label>
                  <Input
                    id="eco-water-body"
                    placeholder="река, водоём, городская сеть"
                    {...form.register("water_body")}
                  />
                  {fieldError("water_body")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-water-permit">Номер разрешения</Label>
                  <Input
                    id="eco-water-permit"
                    placeholder="реквизиты документа"
                    {...form.register("permit_number")}
                  />
                  {fieldError("permit_number")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-water-notes">Заметки</Label>
                <Textarea
                  id="eco-water-notes"
                  rows={3}
                  placeholder="условия разрешения, особенности"
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
