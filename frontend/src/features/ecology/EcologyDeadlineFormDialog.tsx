import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  REPORTING_KIND_TITLES,
  ecologyApi,
  type ReportingDeadlineDto,
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
  ecologyReportingFormSchema,
  type EcologyReportingFormValues,
} from "@/types/forms/ecologyReporting";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyReportingFormValues = {
  kind: "report",
  title: "",
  period: "",
  due_on: "",
  done_on: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyReportingFormValues> = {
  kind: "kind",
  title: "title",
  period: "period",
  due_on: "due_on",
  done_on: "done_on",
  responsible: "responsible",
  notes: "notes",
};

/** Пустая строка в необязательном поле — «не задано», а не пустой текст. */
const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyDeadlineFormDialogProps {
  trigger: ReactNode;
  initialData?: ReportingDeadlineDto;
  onSubmitted?: (deadline: ReportingDeadlineDto) => void;
}

/**
 * Форма срока отчётности или платежа (разд. 55.3, срез-98).
 *
 * До этой формы ручки `POST/PATCH /ecology/reporting-deadlines` (срез-71)
 * были доступны только через API: экран просил «внесите сроки», а вносить
 * было негде. На первом уровне пять полей: вид, что сдать, период, срок и
 * дата исполнения — отметка «сдано/уплачено» и есть главное действие по
 * сроку после его заведения, поэтому она не прячется под «Дополнительно».
 * Ответственный и заметки — под «Дополнительно» (ТЗ разд. 59.3).
 */
export const EcologyDeadlineFormDialog = ({
  trigger,
  initialData,
  onSubmitted,
}: EcologyDeadlineFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyReportingFormValues>({
    resolver: zodResolver(ecologyReportingFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        title: initialData.title,
        period: initialData.period ?? "",
        due_on: initialData.due_on,
        done_on: initialData.done_on ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyReportingFormValues) => {
    // Пустая дата исполнения уходит как null: на правке это снимает отметку
    // «исполнено» (ручка так и задумана), на создании — срок живёт в
    // календаре и Центре внимания до отметки.
    const body = {
      title: values.title.trim(),
      period: orNull(values.period),
      due_on: values.due_on,
      done_on: orNull(values.done_on),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateReportingDeadline(initialData.id, body)
        : await ecologyApi.createReportingDeadline({
            kind: values.kind,
            ...body,
          });
      onSubmitted?.(result);
      toast.success(initialData ? "Срок обновлён" : "Срок внесён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить срок");
      } else {
        toast.error("Не удалось сохранить срок");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyReportingFormValues) => {
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
          <DialogTitle>{isEdit ? "Изменить срок" : "Внести срок"}</DialogTitle>
          <DialogDescription>
            Что сдать или оплатить и к какой дате по нормативному акту.
            Платформа дату не назначает и не вычисляет; внесённый срок виден в
            календаре и Центре внимания до отметки об исполнении.
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
              <Label htmlFor="eco-deadline-kind">Вид</Label>
              {/* Вид задаёт, «сдать» это или «уплатить»; после заведения его
                  не меняют — ручка правки поля не принимает. */}
              <select
                id="eco-deadline-kind"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("kind")}
              >
                {Object.entries(REPORTING_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-deadline-period">Период</Label>
              <Input
                id="eco-deadline-period"
                placeholder="напр. 2025 год, I квартал 2026"
                {...form.register("period")}
              />
              {fieldError("period")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="eco-deadline-title">Что сдать или оплатить</Label>
            <Input
              id="eco-deadline-title"
              placeholder="напр. 2-ТП (отходы) за 2025 год"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-deadline-due">Срок</Label>
              <Input
                id="eco-deadline-due"
                type="date"
                {...form.register("due_on")}
              />
              {fieldError("due_on")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-deadline-done">Дата исполнения</Label>
              <Input
                id="eco-deadline-done"
                type="date"
                title="Пусто — срок ещё не исполнен"
                {...form.register("done_on")}
              />
              {fieldError("done_on")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дополнительно
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="eco-deadline-responsible">Ответственный</Label>
                <Input
                  id="eco-deadline-responsible"
                  placeholder="кто сдаёт или платит"
                  {...form.register("responsible")}
                />
                {fieldError("responsible")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-deadline-notes">Заметки</Label>
                <Textarea
                  id="eco-deadline-notes"
                  rows={3}
                  placeholder="номер нормативного акта, особенности"
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
