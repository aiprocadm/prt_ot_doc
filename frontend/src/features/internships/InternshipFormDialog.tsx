import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  INTERNSHIP_STATUS_TITLES,
  internshipsApi,
  type InternshipDto,
} from "@/api/internships";
import { TRAINING_DISCIPLINE_TITLES } from "@/api/training";
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
  internshipFormSchema,
  shiftsToNumber,
  type InternshipFormValues,
} from "@/types/forms/internships";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: InternshipFormValues = {
  person_id: "",
  mentor_person_id: "",
  discipline: "",
  subject: "",
  planned_shifts: "",
  completed_shifts: "",
  started_on: "",
  finished_on: "",
  status: "planned",
  notes: "",
};

const INTERNSHIP_API_FIELD_MAP: Record<string, keyof InternshipFormValues> = {
  person_id: "person_id",
  mentor_person_id: "mentor_person_id",
  discipline: "discipline",
  subject: "subject",
  planned_shifts: "planned_shifts",
  completed_shifts: "completed_shifts",
  started_on: "started_on",
  finished_on: "finished_on",
  status: "status",
  notes: "notes",
};

/** Пустая строка в необязательном поле — «не задано», а не пустой текст. */
const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface InternshipFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: InternshipDto;
  onSubmitted?: (internship: InternshipDto) => void;
}

/**
 * Форма стажировки — одна на все дисциплины (сущность ядровая, срез-7).
 *
 * На первом уровне семь полей: кто, у кого, на что, какой дисциплиной
 * размечена, план и факт смен, состояние. Сроки и заметки — под
 * «Дополнительно» (ТЗ разд. 59.3): назначая стажировку, даты обычно ещё не
 * знают, а требовать их значило бы заставлять выдумывать.
 */
export const InternshipFormDialog = ({
  trigger,
  persons,
  initialData,
  onSubmitted,
}: InternshipFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<InternshipFormValues>({
    resolver: zodResolver(internshipFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        person_id: initialData.person_id,
        mentor_person_id: initialData.mentor_person_id ?? "",
        discipline: initialData.discipline ?? "",
        subject: initialData.subject ?? "",
        planned_shifts: String(initialData.planned_shifts),
        completed_shifts: String(initialData.completed_shifts),
        started_on: initialData.started_on ?? "",
        finished_on: initialData.finished_on ?? "",
        status: initialData.status,
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: InternshipFormValues) => {
    const body = {
      mentor_person_id: orNull(values.mentor_person_id),
      discipline: orNull(values.discipline),
      subject: orNull(values.subject),
      planned_shifts: shiftsToNumber(values.planned_shifts),
      completed_shifts: shiftsToNumber(values.completed_shifts),
      started_on: orNull(values.started_on),
      finished_on: orNull(values.finished_on),
      status: values.status,
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await internshipsApi.update(initialData.id, body)
        : await internshipsApi.create({ person_id: values.person_id, ...body });
      onSubmitted?.(result);
      toast.success(
        initialData ? "Стажировка обновлена" : "Стажировка назначена",
      );
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, INTERNSHIP_API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить стажировку");
      } else {
        toast.error("Не удалось сохранить стажировку");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof InternshipFormValues) => {
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
            {isEdit ? "Изменить стажировку" : "Назначить стажировку"}
          </DialogTitle>
          <DialogDescription>
            Кто стажируется, у кого и сколько смен по плану. Нужна ли стажировка
            вообще и достаточно ли смен — решает приказ, а не программа.
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
              <Label htmlFor="internship-person">Стажёр</Label>
              <select
                id="internship-person"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("person_id")}
              >
                <option value="">— Выберите работника —</option>
                {persons.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name}
                  </option>
                ))}
              </select>
              {fieldError("person_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="internship-mentor">Наставник</Label>
              <select
                id="internship-mentor"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("mentor_person_id")}
              >
                <option value="">— Не назначен —</option>
                {persons.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name}
                  </option>
                ))}
              </select>
              {fieldError("mentor_person_id")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="internship-subject">На что стажировка</Label>
            <Input
              id="internship-subject"
              placeholder="напр. Водитель автобуса, маршрут № 12"
              {...form.register("subject")}
            />
            {fieldError("subject")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="internship-discipline">Дисциплина</Label>
              <select
                id="internship-discipline"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("discipline")}
              >
                <option value="">— Не размечена —</option>
                {Object.entries(TRAINING_DISCIPLINE_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("discipline")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="internship-status">Состояние</Label>
              <select
                id="internship-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(INTERNSHIP_STATUS_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("status")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="internship-planned">Смен по плану</Label>
              <Input
                id="internship-planned"
                type="number"
                min={0}
                step={1}
                inputMode="numeric"
                {...form.register("planned_shifts")}
              />
              {fieldError("planned_shifts")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="internship-completed">Смен пройдено</Label>
              <Input
                id="internship-completed"
                type="number"
                min={0}
                step={1}
                inputMode="numeric"
                {...form.register("completed_shifts")}
              />
              {fieldError("completed_shifts")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Сроки и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="internship-started">Начата</Label>
                  <Input
                    id="internship-started"
                    type="date"
                    {...form.register("started_on")}
                  />
                  {fieldError("started_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="internship-finished">Окончена</Label>
                  <Input
                    id="internship-finished"
                    type="date"
                    {...form.register("finished_on")}
                  />
                  {fieldError("finished_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="internship-notes">Заметки</Label>
                <Textarea
                  id="internship-notes"
                  rows={3}
                  placeholder="номер приказа, особенности"
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
