import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  EMISSION_SOURCE_KIND_TITLES,
  ecologyApi,
  type EmissionSourceDto,
  type EnvironmentalFacilityDto,
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
  ecologyEmissionSourceFormSchema,
  type EcologyEmissionSourceFormValues,
} from "@/types/forms/ecologyEmission";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyEmissionSourceFormValues = {
  facility_id: "",
  source_number: "",
  name: "",
  kind: "organized",
  location: "",
  inventoried_on: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyEmissionSourceFormValues> = {
  facility_id: "facility_id",
  source_number: "source_number",
  name: "name",
  kind: "kind",
  location: "location",
  inventoried_on: "inventoried_on",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyEmissionSourceFormDialogProps {
  trigger: ReactNode;
  facilities: EnvironmentalFacilityDto[];
  initialData?: EmissionSourceDto;
  onSubmitted?: (source: EmissionSourceDto) => void;
}

/**
 * Форма источника выбросов (разд. 55.2 «инвентаризация», срез-100).
 *
 * Четыре поля на первом уровне: объект НВОС, номер источника, название и вид;
 * место, дата инвентаризации и заметки — под «Дополнительно».
 */
export const EcologyEmissionSourceFormDialog = ({
  trigger,
  facilities,
  initialData,
  onSubmitted,
}: EcologyEmissionSourceFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyEmissionSourceFormValues>({
    resolver: zodResolver(ecologyEmissionSourceFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        facility_id: initialData.facility_id,
        source_number: initialData.source_number,
        name: initialData.name,
        kind: initialData.kind,
        location: initialData.location ?? "",
        inventoried_on: initialData.inventoried_on ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyEmissionSourceFormValues) => {
    const body = {
      facility_id: values.facility_id,
      source_number: values.source_number.trim(),
      name: values.name.trim(),
      kind: values.kind,
      location: orNull(values.location),
      inventoried_on: orNull(values.inventoried_on),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateEmissionSource(initialData.id, body)
        : await ecologyApi.createEmissionSource(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Источник обновлён" : "Источник заведён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить источник");
      } else {
        toast.error("Не удалось сохранить источник");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyEmissionSourceFormValues) => {
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
            {isEdit ? "Изменить источник" : "Завести источник выбросов"}
          </DialogTitle>
          <DialogDescription>
            Сведения из инвентаризации источников. Номер источника уникален в
            пределах объекта НВОС: два одинаковых номера означают, что источник
            заведён дважды.
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
            <Label htmlFor="eco-source-facility">Объект НВОС</Label>
            <select
              id="eco-source-facility"
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
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-source-number">Номер источника</Label>
              <Input
                id="eco-source-number"
                placeholder="напр. 0001"
                {...form.register("source_number")}
              />
              {fieldError("source_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-source-kind">Вид источника</Label>
              <select
                id="eco-source-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(EMISSION_SOURCE_KIND_TITLES).map(
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
          <div className="space-y-2">
            <Label htmlFor="eco-source-name">Источник</Label>
            <Input
              id="eco-source-name"
              placeholder="напр. Труба котельной"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Место, инвентаризация и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="eco-source-location">Место</Label>
                  <Input
                    id="eco-source-location"
                    placeholder="цех, площадка, координаты"
                    {...form.register("location")}
                  />
                  {fieldError("location")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-source-inventoried">
                    Инвентаризация проведена
                  </Label>
                  <Input
                    id="eco-source-inventoried"
                    type="date"
                    {...form.register("inventoried_on")}
                  />
                  {fieldError("inventoried_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-source-notes">Заметки</Label>
                <Textarea
                  id="eco-source-notes"
                  rows={3}
                  placeholder="характеристики, особенности"
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
