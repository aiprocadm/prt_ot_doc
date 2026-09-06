import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  WASTE_HAZARD_CLASS_TITLES,
  ecologyApi,
  type EnvironmentalFacilityDto,
  type WastePassportDto,
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
  ecologyWastePassportFormSchema,
  tonsToPayload,
  type EcologyWastePassportFormValues,
} from "@/types/forms/ecologyWastePassport";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyWastePassportFormValues = {
  name: "",
  fkko_code: "",
  hazard_class: "",
  facility_id: "",
  annual_limit_tons: "",
  approved_on: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyWastePassportFormValues> = {
  name: "name",
  fkko_code: "fkko_code",
  hazard_class: "hazard_class",
  facility_id: "facility_id",
  annual_limit_tons: "annual_limit_tons",
  approved_on: "approved_on",
  notes: "notes",
};

/** Пустая строка в необязательном поле — «не задано», а не пустой текст. */
const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyWastePassportFormDialogProps {
  trigger: ReactNode;
  facilities: EnvironmentalFacilityDto[];
  initialData?: WastePassportDto;
  onSubmitted?: (passport: WastePassportDto) => void;
}

/**
 * Форма паспорта отхода (разд. 55.2, срез-99).
 *
 * На первом уровне пять полей: вид отхода, код ФККО, класс опасности, объект
 * НВОС и годовой лимит; дата утверждения и заметки — под «Дополнительно».
 *
 * ГРАНИЦА, названная и в форме: лимит берётся из НООЛР или декларации —
 * платформа его не рассчитывает; пустой лимит значит «не установлен», и
 * превышения по такому паспорту не бывает по построению. Классов четыре: на
 * отходы V класса паспорт не составляют, и пятого значения в списке нет.
 */
export const EcologyWastePassportFormDialog = ({
  trigger,
  facilities,
  initialData,
  onSubmitted,
}: EcologyWastePassportFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyWastePassportFormValues>({
    resolver: zodResolver(ecologyWastePassportFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        name: initialData.name,
        fkko_code: initialData.fkko_code,
        hazard_class: initialData.hazard_class,
        facility_id: initialData.facility_id ?? "",
        annual_limit_tons: initialData.annual_limit_tons ?? "",
        approved_on: initialData.approved_on ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyWastePassportFormValues) => {
    const body = {
      name: values.name.trim(),
      fkko_code: values.fkko_code.trim(),
      hazard_class: values.hazard_class,
      facility_id: orNull(values.facility_id),
      annual_limit_tons: tonsToPayload(values.annual_limit_tons),
      approved_on: orNull(values.approved_on),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateWastePassport(initialData.id, body)
        : await ecologyApi.createWastePassport(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Паспорт обновлён" : "Паспорт заведён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить паспорт");
      } else {
        toast.error("Не удалось сохранить паспорт");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyWastePassportFormValues) => {
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
            {isEdit ? "Изменить паспорт отхода" : "Завести паспорт отхода"}
          </DialogTitle>
          <DialogDescription>
            Паспорт составляется на отходы I–IV класса: отходы V класса
            паспортизации не подлежат. Годовой лимит вносится из документа
            (НООЛР или декларации) — платформа его не рассчитывает.
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
            <Label htmlFor="eco-passport-name">Вид отхода</Label>
            <Input
              id="eco-passport-name"
              placeholder="напр. Отходы минеральных масел моторных"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-passport-fkko">Код ФККО</Label>
              <Input
                id="eco-passport-fkko"
                placeholder="4 06 110 01 31 3"
                {...form.register("fkko_code")}
              />
              {fieldError("fkko_code")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-passport-class">Класс опасности</Label>
              <select
                id="eco-passport-class"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("hazard_class")}
              >
                <option value="">— Выберите класс —</option>
                {Object.entries(WASTE_HAZARD_CLASS_TITLES).map(
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
              <Label htmlFor="eco-passport-facility">Объект НВОС</Label>
              <select
                id="eco-passport-facility"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("facility_id")}
              >
                <option value="">— Не привязан —</option>
                {facilities.map((facility) => (
                  <option key={facility.id} value={facility.id}>
                    {facility.name}
                  </option>
                ))}
              </select>
              {fieldError("facility_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-passport-limit">Годовой лимит, т</Label>
              <Input
                id="eco-passport-limit"
                inputMode="decimal"
                placeholder="пусто — не установлен"
                title="Из НООЛР или декларации; без лимита превышения не бывает"
                {...form.register("annual_limit_tons")}
              />
              {fieldError("annual_limit_tons")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дата утверждения и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="eco-passport-approved">Паспорт утверждён</Label>
                <Input
                  id="eco-passport-approved"
                  type="date"
                  {...form.register("approved_on")}
                />
                {fieldError("approved_on")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-passport-notes">Заметки</Label>
                <Textarea
                  id="eco-passport-notes"
                  rows={3}
                  placeholder="реквизиты НООЛР, оператор по обращению"
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
