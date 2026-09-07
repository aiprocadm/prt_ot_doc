import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  DRIVER_LICENSE_CATEGORY_TITLES,
  DRIVER_STATUS_TITLES,
  roadSafetyApi,
  type DriverDto,
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
import type { PersonDto } from "@/types/dto/persons";
import {
  driverFormSchema,
  type DriverFormValues,
} from "@/types/forms/roadSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: DriverFormValues = {
  person_id: "",
  license_number: "",
  categories: [],
  license_due: "",
  status: "admitted",
  license_issued_at: "",
  experience_since: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof DriverFormValues> = {
  person_id: "person_id",
  license_number: "license_number",
  categories: "categories",
  license_due: "license_due",
  status: "status",
  license_issued_at: "license_issued_at",
  experience_since: "experience_since",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface DriverFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: DriverDto;
  onSubmitted?: (driver: DriverDto) => void;
}

/**
 * Форма карточки водителя (разд. 56.2, срез-107).
 *
 * Пять полей на первом уровне: работник, номер удостоверения, категории,
 * срок действия и состояние допуска; дата выдачи, начало стажа и заметки —
 * под «Дополнительно».
 *
 * ГРАНИЦЫ: ФИО в карточке нет — человек берётся из ядра, поэтому при правке
 * работник заперт (ручка PATCH его не принимает: другой человек — другая
 * карточка). Стаж задаётся ДАТОЙ начала, а не числом лет: записанное «3 года»
 * через два года молча стало бы ложью. Полей «допущен ли к этой машине» и
 * «хватает ли стажа» нет — это следует из массы ТС, числа мест и вида
 * перевозок по закону.
 */
export const DriverFormDialog = ({
  trigger,
  persons,
  initialData,
  onSubmitted,
}: DriverFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<DriverFormValues>({
    resolver: zodResolver(driverFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        person_id: initialData.person_id,
        license_number: initialData.license_number,
        categories: initialData.categories,
        license_due: initialData.license_due ?? "",
        status: initialData.status,
        license_issued_at: initialData.license_issued_at ?? "",
        experience_since: initialData.experience_since ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: DriverFormValues) => {
    const common = {
      license_number: values.license_number.trim(),
      categories: values.categories,
      license_issued_at: orNull(values.license_issued_at),
      license_due: orNull(values.license_due),
      experience_since: orNull(values.experience_since),
      status: values.status,
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await roadSafetyApi.updateDriver(initialData.id, common)
        : await roadSafetyApi.createDriver({
            person_id: values.person_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Карточка обновлена" : "Водитель заведён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить карточку водителя");
      } else {
        toast.error("Не удалось сохранить карточку водителя");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof DriverFormValues) => {
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
            {isEdit ? "Изменить карточку водителя" : "Завести водителя"}
          </DialogTitle>
          <DialogDescription>
            Карточка допуска к управлению: удостоверение, категории и стаж. Стаж
            задаётся датой, с которой он идёт, — число лет считает система.
            Хватает ли категории и стажа для конкретной машины, определяет
            закон, а не платформа.
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
              <Label htmlFor="drv-person">Работник</Label>
              <select
                id="drv-person"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("person_id")}
              >
                <option value="">— Выберите работника —</option>
                {persons.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
              {fieldError("person_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="drv-license">Номер удостоверения</Label>
              <Input
                id="drv-license"
                placeholder="99 99 123456"
                {...form.register("license_number")}
              />
              {fieldError("license_number")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="drv-categories">Категории</Label>
            {/* Отметки, а не выпадающий список: категорий у водителя обычно
                несколько, и они читаются глазами целиком. По UX-бюджету это
                один вопрос, а не шестнадцать полей. */}
            <div
              id="drv-categories"
              className="flex flex-wrap gap-2 rounded-md border p-2"
            >
              {Object.entries(DRIVER_LICENSE_CATEGORY_TITLES).map(
                ([code, title]) => (
                  <label
                    key={code}
                    className="flex items-center gap-1 text-sm"
                    title={title}
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      value={code}
                      {...form.register("categories")}
                    />
                    {code}
                  </label>
                ),
              )}
            </div>
            {fieldError("categories")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="drv-license-due">Удостоверение до</Label>
              <Input
                id="drv-license-due"
                type="date"
                title="Пусто — сведения не внесены"
                {...form.register("license_due")}
              />
              {fieldError("license_due")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="drv-status">Допуск</Label>
              <select
                id="drv-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(DRIVER_STATUS_TITLES).map(([code, title]) => (
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
              Выдача удостоверения, стаж и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="drv-issued">Удостоверение выдано</Label>
                  <Input
                    id="drv-issued"
                    type="date"
                    {...form.register("license_issued_at")}
                  />
                  {fieldError("license_issued_at")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="drv-experience">Стаж с</Label>
                  <Input
                    id="drv-experience"
                    type="date"
                    title="Число лет считает система по этой дате"
                    {...form.register("experience_since")}
                  />
                  {fieldError("experience_since")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="drv-notes">Заметки</Label>
                <Textarea
                  id="drv-notes"
                  rows={3}
                  placeholder="ограничения, особые отметки"
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
