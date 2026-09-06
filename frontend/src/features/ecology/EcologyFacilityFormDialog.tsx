import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  NVOS_CATEGORY_TITLES,
  NVOS_STATUS_TITLES,
  ecologyApi,
  type EnvironmentalFacilityDto,
} from "@/api/ecology";
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
  ecologyFacilityFormSchema,
  type EcologyFacilityFormValues,
} from "@/types/forms/ecologyFacility";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyFacilityFormValues = {
  name: "",
  register_number: "",
  category: "",
  site_id: "",
  status: "registered",
  registered_on: "",
  actualized_on: "",
  excluded_on: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyFacilityFormValues> = {
  name: "name",
  register_number: "register_number",
  category: "category",
  site_id: "site_id",
  status: "status",
  registered_on: "registered_on",
  actualized_on: "actualized_on",
  excluded_on: "excluded_on",
  responsible: "responsible",
  notes: "notes",
};

/** Пустая строка в необязательном поле — «не задано», а не пустой текст. */
const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyFacilityFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: EnvironmentalFacilityDto;
  onSubmitted?: (facility: EnvironmentalFacilityDto) => void;
}

/**
 * Форма объекта НВОС (разд. 55.1, срез-99).
 *
 * До неё ручки `POST/PATCH /ecology/facilities` (срез-1) были доступны только
 * через API: экран звал «внесите объекты из свидетельства», а внести их было
 * негде. На первом уровне пять полей — название, код в реестре, категория,
 * площадка и состояние; даты, ответственный и заметки — под «Дополнительно»
 * (ТЗ разд. 59.3).
 *
 * ГРАНИЦА: категорию платформа не вычисляет и не подсказывает — её присвоили
 * при постановке на государственный учёт, форма лишь переносит внесённое.
 */
export const EcologyFacilityFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: EcologyFacilityFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyFacilityFormValues>({
    resolver: zodResolver(ecologyFacilityFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        name: initialData.name,
        register_number: initialData.register_number,
        category: initialData.category,
        site_id: initialData.site_id ?? "",
        status: initialData.status,
        registered_on: initialData.registered_on ?? "",
        actualized_on: initialData.actualized_on ?? "",
        excluded_on: initialData.excluded_on ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyFacilityFormValues) => {
    const body = {
      name: values.name.trim(),
      register_number: values.register_number.trim(),
      category: values.category,
      site_id: orNull(values.site_id),
      status: values.status,
      registered_on: orNull(values.registered_on),
      actualized_on: orNull(values.actualized_on),
      excluded_on: orNull(values.excluded_on),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateFacility(initialData.id, body)
        : await ecologyApi.createFacility(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Объект обновлён" : "Объект заведён");
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

  const fieldError = (name: keyof EcologyFacilityFormValues) => {
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
            {isEdit ? "Изменить объект НВОС" : "Завести объект НВОС"}
          </DialogTitle>
          <DialogDescription>
            Сведения из свидетельства о постановке на государственный учёт.
            Категорию присваивает надзор при постановке — платформа её не
            вычисляет и не подсказывает.
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
            <Label htmlFor="eco-facility-name">Объект</Label>
            <Input
              id="eco-facility-name"
              placeholder="напр. Производственная площадка №1"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-facility-register">Код в реестре</Label>
              <Input
                id="eco-facility-register"
                placeholder="12-0177-001234-П"
                {...form.register("register_number")}
              />
              {fieldError("register_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-facility-category">Категория</Label>
              <select
                id="eco-facility-category"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("category")}
              >
                <option value="">— Выберите категорию —</option>
                {Object.entries(NVOS_CATEGORY_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("category")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-facility-site">Площадка</Label>
              <select
                id="eco-facility-site"
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
              <Label htmlFor="eco-facility-status">Состояние</Label>
              {/* Снятие с учёта — не удаление: история воздействия, отчётность
                  и платежи по объекту остаются. */}
              <select
                id="eco-facility-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(NVOS_STATUS_TITLES).map(([code, title]) => (
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
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="eco-facility-registered">На учёте с</Label>
                  <Input
                    id="eco-facility-registered"
                    type="date"
                    {...form.register("registered_on")}
                  />
                  {fieldError("registered_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-facility-actualized">
                    Сведения актуализированы
                  </Label>
                  <Input
                    id="eco-facility-actualized"
                    type="date"
                    {...form.register("actualized_on")}
                  />
                  {fieldError("actualized_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eco-facility-excluded">Снят с учёта</Label>
                  <Input
                    id="eco-facility-excluded"
                    type="date"
                    {...form.register("excluded_on")}
                  />
                  {fieldError("excluded_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-facility-responsible">Ответственный</Label>
                <Input
                  id="eco-facility-responsible"
                  placeholder="эколог предприятия"
                  {...form.register("responsible")}
                />
                {fieldError("responsible")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-facility-notes">Заметки</Label>
                <Textarea
                  id="eco-facility-notes"
                  rows={3}
                  placeholder="реквизиты свидетельства, особенности"
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
