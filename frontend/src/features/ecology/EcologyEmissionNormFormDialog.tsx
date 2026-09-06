import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  ecologyApi,
  type EmissionNormDto,
  type EmissionSourceDto,
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
  ecologyEmissionNormFormSchema,
  numberToPayload,
  type EcologyEmissionNormFormValues,
} from "@/types/forms/ecologyEmission";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyEmissionNormFormValues = {
  source_id: "",
  substance: "",
  limit_grams_per_second: "",
  limit_tons_per_year: "",
  permit_number: "",
  valid_until: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyEmissionNormFormValues> = {
  source_id: "source_id",
  substance: "substance",
  limit_grams_per_second: "limit_grams_per_second",
  limit_tons_per_year: "limit_tons_per_year",
  permit_number: "permit_number",
  valid_until: "valid_until",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyEmissionNormFormDialogProps {
  trigger: ReactNode;
  sources: EmissionSourceDto[];
  initialData?: EmissionNormDto;
  onSubmitted?: (norm: EmissionNormDto) => void;
}

/**
 * Форма норматива выброса — ПДВ/НДВ (разд. 55.2, срез-100).
 *
 * Шесть полей на первом уровне: источник, вещество, два предела, номер
 * разрешения и срок его действия; заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: пустой срок разрешения означает БЕССРОЧНО, а не «просрочено» (для
 * объектов III категории нормативы бывают без срока) — так же считает и
 * сервер. Величины пределов платформа не выводит: они установлены
 * разрешением, форма лишь переносит их.
 */
export const EcologyEmissionNormFormDialog = ({
  trigger,
  sources,
  initialData,
  onSubmitted,
}: EcologyEmissionNormFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyEmissionNormFormValues>({
    resolver: zodResolver(ecologyEmissionNormFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        source_id: initialData.source_id,
        substance: initialData.substance,
        limit_grams_per_second: initialData.limit_grams_per_second ?? "",
        limit_tons_per_year: initialData.limit_tons_per_year ?? "",
        permit_number: initialData.permit_number ?? "",
        valid_until: initialData.valid_until ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyEmissionNormFormValues) => {
    const body = {
      source_id: values.source_id,
      substance: values.substance.trim(),
      limit_grams_per_second: numberToPayload(values.limit_grams_per_second),
      limit_tons_per_year: numberToPayload(values.limit_tons_per_year),
      permit_number: orNull(values.permit_number),
      valid_until: orNull(values.valid_until),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateEmissionNorm(initialData.id, body)
        : await ecologyApi.createEmissionNorm(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Норматив обновлён" : "Норматив внесён");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить норматив");
      } else {
        toast.error("Не удалось сохранить норматив");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyEmissionNormFormValues) => {
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
            {isEdit ? "Изменить норматив" : "Внести норматив"}
          </DialogTitle>
          <DialogDescription>
            Величины ПДВ/НДВ установлены разрешением — платформа их не
            рассчитывает. Пустой срок разрешения означает «бессрочно», а не
            «просрочено».
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
              <Label htmlFor="eco-norm-source">Источник выбросов</Label>
              <select
                id="eco-norm-source"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("source_id")}
              >
                <option value="">— Выберите источник —</option>
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    №{source.source_number} · {source.name}
                  </option>
                ))}
              </select>
              {fieldError("source_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-norm-substance">Вещество</Label>
              <Input
                id="eco-norm-substance"
                placeholder="напр. Азота диоксид"
                {...form.register("substance")}
              />
              {fieldError("substance")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-norm-gps">Предел, г/с</Label>
              <Input
                id="eco-norm-gps"
                inputMode="decimal"
                placeholder="из разрешения"
                {...form.register("limit_grams_per_second")}
              />
              {fieldError("limit_grams_per_second")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-norm-tpy">Предел, т/год</Label>
              <Input
                id="eco-norm-tpy"
                inputMode="decimal"
                placeholder="из разрешения"
                {...form.register("limit_tons_per_year")}
              />
              {fieldError("limit_tons_per_year")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-norm-permit">Номер разрешения</Label>
              <Input
                id="eco-norm-permit"
                placeholder="реквизиты документа"
                {...form.register("permit_number")}
              />
              {fieldError("permit_number")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-norm-valid">Разрешение действует до</Label>
              <Input
                id="eco-norm-valid"
                type="date"
                title="Пусто — бессрочно"
                {...form.register("valid_until")}
              />
              {fieldError("valid_until")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дополнительно
            </summary>
            <div className="mt-3 space-y-2">
              <Label htmlFor="eco-norm-notes">Заметки</Label>
              <Textarea
                id="eco-norm-notes"
                rows={3}
                placeholder="условия разрешения, особенности"
                {...form.register("notes")}
              />
              {fieldError("notes")}
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
