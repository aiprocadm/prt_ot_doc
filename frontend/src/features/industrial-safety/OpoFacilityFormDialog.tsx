import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  OPO_HAZARD_CLASS_TITLES,
  OPO_STATUS_TITLES,
  industrialSafetyApi,
  type HazardousFacilityDto,
} from "@/api/industrialSafety";
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
  opoFacilityFormSchema,
  type OpoFacilityFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: OpoFacilityFormValues = {
  name: "",
  register_number: "",
  hazard_class: "",
  site_id: "",
  status: "registered",
  registered_on: "",
  excluded_on: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof OpoFacilityFormValues> = {
  name: "name",
  register_number: "register_number",
  hazard_class: "hazard_class",
  site_id: "site_id",
  status: "status",
  registered_on: "registered_on",
  excluded_on: "excluded_on",
  responsible: "responsible",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface OpoFacilityFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: HazardousFacilityDto;
  onSubmitted?: (facility: HazardousFacilityDto) => void;
}

/**
 * Форма опасного производственного объекта (разд. 54.2, срез-105).
 *
 * Пять полей на первом уровне: наименование, номер в госреестре, класс
 * опасности, площадка и состояние; даты, ответственный и заметки — под
 * «Дополнительно» (ТЗ разд. 59.3).
 *
 * ГРАНИЦА: класс опасности присваивают при регистрации по признакам объекта —
 * платформа его не вычисляет и не подсказывает. Исключение из реестра —
 * состояние, а не удаление: история эксплуатации и документы остаются.
 */
export const OpoFacilityFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: OpoFacilityFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<OpoFacilityFormValues>({
    resolver: zodResolver(opoFacilityFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        name: initialData.name,
        register_number: initialData.register_number,
        hazard_class: initialData.hazard_class,
        site_id: initialData.site_id ?? "",
        status: initialData.status,
        registered_on: initialData.registered_on ?? "",
        excluded_on: initialData.excluded_on ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: OpoFacilityFormValues) => {
    const body = {
      name: values.name.trim(),
      register_number: values.register_number.trim(),
      hazard_class: values.hazard_class,
      site_id: orNull(values.site_id),
      status: values.status,
      registered_on: orNull(values.registered_on),
      excluded_on: orNull(values.excluded_on),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await industrialSafetyApi.updateFacility(initialData.id, body)
        : await industrialSafetyApi.createFacility(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Объект обновлён" : "Объект зарегистрирован");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить объект");
      } else {
        toast.error("Не удалось сохранить объект");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof OpoFacilityFormValues) => {
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
            {isEdit ? "Изменить объект" : "Завести объект (ОПО)"}
          </DialogTitle>
          <DialogDescription>
            Сведения из свидетельства о регистрации в госреестре ОПО. Класс
            опасности присваивает надзор при регистрации — платформа его не
            вычисляет.
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
            <Label htmlFor="opo-facility-name">Объект</Label>
            <Input
              id="opo-facility-name"
              placeholder="напр. Площадка склада ГСМ"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="opo-facility-register">Номер в реестре</Label>
              <Input
                id="opo-facility-register"
                placeholder="А01-12345-0001"
                {...form.register("register_number")}
              />
              {fieldError("register_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-facility-class">Класс опасности</Label>
              <select
                id="opo-facility-class"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("hazard_class")}
              >
                <option value="">— Выберите класс —</option>
                {Object.entries(OPO_HAZARD_CLASS_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("hazard_class")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="opo-facility-site">Площадка</Label>
              <select
                id="opo-facility-site"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("site_id")}
              >
                <option value="">— Не привязан —</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
              {fieldError("site_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-facility-status">Состояние</Label>
              <select
                id="opo-facility-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(OPO_STATUS_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("status")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Даты, ответственный и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="opo-facility-registered">
                    Зарегистрирован
                  </Label>
                  <Input
                    id="opo-facility-registered"
                    type="date"
                    {...form.register("registered_on")}
                  />
                  {fieldError("registered_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="opo-facility-excluded">Исключён</Label>
                  <Input
                    id="opo-facility-excluded"
                    type="date"
                    {...form.register("excluded_on")}
                  />
                  {fieldError("excluded_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="opo-facility-responsible">Ответственный</Label>
                <Input
                  id="opo-facility-responsible"
                  placeholder="ответственный за эксплуатацию"
                  {...form.register("responsible")}
                />
                {fieldError("responsible")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="opo-facility-notes">Заметки</Label>
                <Textarea
                  id="opo-facility-notes"
                  rows={3}
                  placeholder="состав объекта, особенности"
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
