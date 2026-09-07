import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  ATTESTATION_STATUS_TITLES,
  OPO_ATTESTATION_AREA_TITLES,
  attestationsApi,
} from "@/api/attestations";
import type { OpoAttestationDto } from "@/api/industrialSafety";
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
  opoAttestationFormSchema,
  type OpoAttestationFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: OpoAttestationFormValues = {
  person_id: "",
  area_code: "",
  name: "",
  status: "active",
  issued_at: "",
  expires_at: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof OpoAttestationFormValues> = {
  person_id: "person_id",
  area_code: "area_code",
  name: "name",
  status: "status",
  issued_at: "issued_at",
  expires_at: "expires_at",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface OpoAttestationFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: OpoAttestationDto;
  onSubmitted?: () => void;
}

/**
 * Форма аттестации по промышленной безопасности (разд. 54.2, срез-106).
 *
 * Пять полей на первом уровне: работник, область, название, состояние и срок
 * действия; дата выдачи и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: сущность ЯДРОВАЯ (`/attestations`) — аттестации бывают и у других
 * дисциплин, поэтому в форме контура область ограничена областями
 * промбезопасности: контур отбирает свои записи по дисциплине области, а не по
 * «поле заполнено». Область здесь обязательна, хотя сервер разрешает пустую:
 * запись без области существовала бы, но на этот экран не попала бы никогда.
 */
export const OpoAttestationFormDialog = ({
  trigger,
  persons,
  initialData,
  onSubmitted,
}: OpoAttestationFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<OpoAttestationFormValues>({
    resolver: zodResolver(opoAttestationFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        person_id: initialData.person_id,
        area_code: initialData.area_code,
        name: initialData.name,
        status: "active",
        issued_at: initialData.issued_at ?? "",
        expires_at: initialData.expires_at ?? "",
        notes: "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: OpoAttestationFormValues) => {
    const body = {
      person_id: values.person_id,
      area_code: values.area_code,
      name: values.name.trim(),
      status: values.status,
      issued_at: orNull(values.issued_at),
      expires_at: orNull(values.expires_at),
      notes: orNull(values.notes),
    };
    try {
      if (initialData) {
        await attestationsApi.update(initialData.id, body);
      } else {
        await attestationsApi.create(body);
      }
      onSubmitted?.();
      toast.success(isEdit ? "Аттестация обновлена" : "Аттестация внесена");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить аттестацию");
      } else {
        toast.error("Не удалось сохранить аттестацию");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof OpoAttestationFormValues) => {
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
            {isEdit ? "Изменить аттестацию" : "Внести аттестацию"}
          </DialogTitle>
          <DialogDescription>
            Сведения из протокола аттестационной комиссии. Область выбирается из
            перечня промышленной безопасности: именно по ней контур отбирает
            свои записи среди всех аттестаций.
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
            <Label htmlFor="opo-att-person">Работник</Label>
            <select
              id="opo-att-person"
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
            <Label htmlFor="opo-att-area">Область аттестации</Label>
            <select
              id="opo-att-area"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("area_code")}
            >
              <option value="">— Выберите область —</option>
              {Object.entries(OPO_ATTESTATION_AREA_TITLES).map(
                ([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ),
              )}
            </select>
            {fieldError("area_code")}
          </div>
          <div className="space-y-2">
            <Label htmlFor="opo-att-name">Аттестация</Label>
            <Input
              id="opo-att-name"
              placeholder="напр. Аттестация по промбезопасности Б.9"
              {...form.register("name")}
            />
            {fieldError("name")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="opo-att-status">Состояние</Label>
              <select
                id="opo-att-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(ATTESTATION_STATUS_TITLES).map(
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
              <Label htmlFor="opo-att-expires">Действует до</Label>
              <Input
                id="opo-att-expires"
                type="date"
                title="Пусто — срок не указан; это отдельное состояние, а не просрочка"
                {...form.register("expires_at")}
              />
              {fieldError("expires_at")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дата выдачи и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="opo-att-issued">Выдана</Label>
                <Input
                  id="opo-att-issued"
                  type="date"
                  {...form.register("issued_at")}
                />
                {fieldError("issued_at")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="opo-att-notes">Заметки</Label>
                <Textarea
                  id="opo-att-notes"
                  rows={3}
                  placeholder="номер протокола, состав комиссии"
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
