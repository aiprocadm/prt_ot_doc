import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  CD_GO_CATEGORY_TITLES,
  civilDefenseApi,
  type ProfileDto,
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
  cdProfileFormSchema,
  type CdProfileFormValues,
} from "@/types/forms/civilDefense";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: CdProfileFormValues = {
  site_id: "",
  category: "none",
  decision_number: "",
  decision_date: "",
  responsible: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof CdProfileFormValues> = {
  site_id: "site_id",
  category: "category",
  decision_number: "decision_number",
  decision_date: "decision_date",
  responsible: "responsible",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface CdProfileFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: ProfileDto;
  onSubmitted?: (profile: ProfileDto) => void;
}

/**
 * Форма сведений по ГО об объекте (разд. 56.1, срез-110).
 *
 * Четыре поля на первом уровне: площадка, категория, номер и дата решения о
 * категорировании; ответственный и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: категорирование выполняет ОРГАН — платформа категорию не предлагает
 * и не выводит; «категория не присвоена» это полноценный ответ, а не пустое
 * поле. На объект заводится одна карточка сведений — повтор сервер отвергает
 * словами. Площадку при правке не меняют: это сведения другого объекта.
 */
export const CdProfileFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: CdProfileFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<CdProfileFormValues>({
    resolver: zodResolver(cdProfileFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        site_id: initialData.site_id,
        category: initialData.category,
        decision_number: initialData.decision_number ?? "",
        decision_date: initialData.decision_date ?? "",
        responsible: initialData.responsible ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: CdProfileFormValues) => {
    const common = {
      category: values.category,
      decision_number: orNull(values.decision_number),
      decision_date: orNull(values.decision_date),
      responsible: orNull(values.responsible),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await civilDefenseApi.updateProfile(initialData.id, common)
        : await civilDefenseApi.createProfile({
            site_id: values.site_id,
            ...common,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Сведения обновлены" : "Сведения по ГО внесены");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить сведения");
      } else {
        toast.error("Не удалось сохранить сведения");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof CdProfileFormValues) => {
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
            {isEdit ? "Изменить сведения по ГО" : "Внести сведения по ГО"}
          </DialogTitle>
          <DialogDescription>
            Категорирование выполняет орган управления ГОЧС: платформа категорию
            не предлагает и хранит внесённую. «Категория не присвоена» — это
            ответ, а не пропуск.
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
              <Label htmlFor="cd-profile-site">Площадка</Label>
              <select
                id="cd-profile-site"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("site_id")}
              >
                <option value="">— Выберите площадку —</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
              {fieldError("site_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-profile-category">Категория по ГО</Label>
              <select
                id="cd-profile-category"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("category")}
              >
                {Object.entries(CD_GO_CATEGORY_TITLES).map(([code, title]) => (
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
              <Label htmlFor="cd-profile-decision">Решение №</Label>
              <Input
                id="cd-profile-decision"
                placeholder="реквизиты решения о категорировании"
                {...form.register("decision_number")}
              />
              {fieldError("decision_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-profile-decision-date">Дата решения</Label>
              <Input
                id="cd-profile-decision-date"
                type="date"
                {...form.register("decision_date")}
              />
              {fieldError("decision_date")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Ответственный и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="cd-profile-responsible">Ответственный</Label>
                <Input
                  id="cd-profile-responsible"
                  placeholder="уполномоченный по ГО и ЧС"
                  {...form.register("responsible")}
                />
                {fieldError("responsible")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-profile-notes">Заметки</Label>
                <Textarea
                  id="cd-profile-notes"
                  rows={3}
                  placeholder="особенности объекта"
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
