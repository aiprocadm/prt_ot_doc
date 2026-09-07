import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FIRE_DOCUMENT_KIND_TITLES,
  fireSafetyApi,
  type FireDocumentDto,
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
import { Textarea } from "@/components/ui/textarea";
import {
  fireDocumentFormSchema,
  type FireDocumentFormValues,
} from "@/types/forms/fireSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: FireDocumentFormValues = {
  kind: "order",
  title: "",
  site_id: "",
  number: "",
  review_due: "",
  approved_on: "",
  location: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof FireDocumentFormValues> = {
  kind: "kind",
  title: "title",
  site_id: "site_id",
  number: "number",
  review_due: "review_due",
  approved_on: "approved_on",
  location: "location",
  responsible: "responsible",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface FireDocumentFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: FireDocumentDto;
  onSubmitted?: (document: FireDocumentDto) => void;
}

/**
 * Форма документа ПБ (разд. 54.1, срез-103).
 *
 * Пять полей на первом уровне: вид, название, площадка, номер и срок
 * пересмотра; дата утверждения, помещение, ответственный и заметки — под
 * «Дополнительно» (ТЗ разд. 59.3).
 *
 * ГРАНИЦА (та же, что названа на экране реестра): платформа НЕ объявляет,
 * какие документы объекту обязательны — декларация нужна не всем объектам,
 * план эвакуации не всем этажам, признаков применимости в данных нет. Пустой
 * срок пересмотра означает «бессрочный», а не «просрочен».
 */
export const FireDocumentFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: FireDocumentFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<FireDocumentFormValues>({
    resolver: zodResolver(fireDocumentFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        title: initialData.title,
        site_id: initialData.site_id ?? "",
        number: initialData.number ?? "",
        review_due: initialData.review_due ?? "",
        approved_on: initialData.approved_on ?? "",
        location: initialData.location ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: FireDocumentFormValues) => {
    const body = {
      kind: values.kind,
      title: values.title.trim(),
      site_id: orNull(values.site_id),
      number: orNull(values.number),
      review_due: orNull(values.review_due),
      approved_on: orNull(values.approved_on),
      location: orNull(values.location),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await fireSafetyApi.updateDocument(initialData.id, body)
        : await fireSafetyApi.createDocument(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Документ обновлён" : "Документ заведён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить документ");
      } else {
        toast.error("Не удалось сохранить документ");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof FireDocumentFormValues) => {
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
            {isEdit ? "Изменить документ" : "Завести документ ПБ"}
          </DialogTitle>
          <DialogDescription>
            Реестр хранит то, что вы завели, и срок пересмотра. Какие документы
            обязательны именно для вашего объекта, определяет специалист —
            платформа этого не решает. Пустой срок означает «бессрочный».
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
              <Label htmlFor="fire-doc-kind">Вид документа</Label>
              <select
                id="fire-doc-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(FIRE_DOCUMENT_KIND_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="fire-doc-number">Номер</Label>
              <Input
                id="fire-doc-number"
                placeholder="реквизиты документа"
                {...form.register("number")}
              />
              {fieldError("number")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="fire-doc-title">Документ</Label>
            <Input
              id="fire-doc-title"
              placeholder="напр. Приказ о назначении ответственного за ПБ"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="fire-doc-site">Площадка</Label>
              <select
                id="fire-doc-site"
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
              <Label htmlFor="fire-doc-review">Пересмотр до</Label>
              <Input
                id="fire-doc-review"
                type="date"
                title="Пусто — документ бессрочный"
                {...form.register("review_due")}
              />
              {fieldError("review_due")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Утверждение, помещение и ответственный
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fire-doc-approved">Утверждён</Label>
                  <Input
                    id="fire-doc-approved"
                    type="date"
                    {...form.register("approved_on")}
                  />
                  {fieldError("approved_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fire-doc-location">Помещение</Label>
                  <Input
                    id="fire-doc-location"
                    placeholder="для инструкции по помещению"
                    {...form.register("location")}
                  />
                  {fieldError("location")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="fire-doc-responsible">Ответственный</Label>
                <Input
                  id="fire-doc-responsible"
                  placeholder="кто отвечает за документ"
                  {...form.register("responsible")}
                />
                {fieldError("responsible")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="fire-doc-notes">Заметки</Label>
                <Textarea
                  id="fire-doc-notes"
                  rows={3}
                  placeholder="где хранится оригинал, особенности"
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
