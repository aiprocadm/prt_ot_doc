import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  CD_DOCUMENT_KIND_TITLES,
  civilDefenseApi,
  type CdDocumentDto,
} from "@/api/civilDefense";
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
  cdDocumentFormSchema,
  type CdDocumentFormValues,
} from "@/types/forms/civilDefense";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: CdDocumentFormValues = {
  kind: "plan_go",
  title: "",
  number: "",
  site_id: "",
  review_due: "",
  approved_on: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof CdDocumentFormValues> = {
  kind: "kind",
  title: "title",
  number: "number",
  site_id: "site_id",
  review_due: "review_due",
  approved_on: "approved_on",
  responsible: "responsible",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface CdDocumentFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: CdDocumentDto;
  onSubmitted?: (document: CdDocumentDto) => void;
}

/**
 * Форма документа планирования ГО (разд. 56.1, срез-110).
 *
 * Пять полей на первом уровне: вид, название, номер, площадка и срок
 * пересмотра; утверждение, ответственный и заметки — под «Дополнительно».
 *
 * ГРАНИЦА (та же, что у документов ПБ в срезе-103): платформа НЕ объявляет,
 * какие документы объекту обязательны — состав планирования зависит от
 * категории по ГО и решений органа. Пустой срок пересмотра означает
 * «бессрочный», а не «просрочен».
 */
export const CdDocumentFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: CdDocumentFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<CdDocumentFormValues>({
    resolver: zodResolver(cdDocumentFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        title: initialData.title,
        number: initialData.number ?? "",
        site_id: initialData.site_id ?? "",
        review_due: initialData.review_due ?? "",
        approved_on: initialData.approved_on ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: CdDocumentFormValues) => {
    const body = {
      kind: values.kind,
      title: values.title.trim(),
      number: orNull(values.number),
      site_id: orNull(values.site_id),
      review_due: orNull(values.review_due),
      approved_on: orNull(values.approved_on),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await civilDefenseApi.updateDocument(initialData.id, body)
        : await civilDefenseApi.createDocument(body);
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

  const fieldError = (name: keyof CdDocumentFormValues) => {
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
            {isEdit ? "Изменить документ" : "Завести документ ГО"}
          </DialogTitle>
          <DialogDescription>
            Реестр хранит то, что вы завели, и срок пересмотра. Какие документы
            обязательны именно вашему объекту, зависит от категории по ГО и
            решений органа — платформа этого не решает. Пустой срок означает
            «бессрочный».
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
              <Label htmlFor="cd-doc-kind">Вид документа</Label>
              <select
                id="cd-doc-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(CD_DOCUMENT_KIND_TITLES).map(
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
              <Label htmlFor="cd-doc-number">Номер</Label>
              <Input
                id="cd-doc-number"
                placeholder="реквизиты документа"
                {...form.register("number")}
              />
              {fieldError("number")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cd-doc-title">Документ</Label>
            <Input
              id="cd-doc-title"
              placeholder="напр. План гражданской обороны организации"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="cd-doc-site">Площадка</Label>
              <select
                id="cd-doc-site"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("site_id")}
              >
                <option value="">— Организация в целом —</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
              {fieldError("site_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-doc-review">Пересмотр до</Label>
              <Input
                id="cd-doc-review"
                type="date"
                title="Пусто — документ бессрочный"
                {...form.register("review_due")}
              />
              {fieldError("review_due")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Утверждение, ответственный и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cd-doc-approved">Утверждён</Label>
                  <Input
                    id="cd-doc-approved"
                    type="date"
                    {...form.register("approved_on")}
                  />
                  {fieldError("approved_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cd-doc-responsible">Ответственный</Label>
                  <Input
                    id="cd-doc-responsible"
                    placeholder="кто отвечает за документ"
                    {...form.register("responsible")}
                  />
                  {fieldError("responsible")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-doc-notes">Заметки</Label>
                <Textarea
                  id="cd-doc-notes"
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
