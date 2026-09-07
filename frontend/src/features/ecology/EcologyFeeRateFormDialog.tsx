import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FEE_IMPACT_KIND_TITLES,
  ecologyApi,
  type FeeRateDto,
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
  ecologyFeeRateFormSchema,
  feeNumberToPayload,
  type EcologyFeeRateFormValues,
} from "@/types/forms/ecologyFee";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyFeeRateFormValues = {
  year: String(new Date().getFullYear()),
  impact_kind: "emission",
  subject: "",
  rate_per_ton: "",
  source_document: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyFeeRateFormValues> = {
  year: "year",
  impact_kind: "impact_kind",
  subject: "subject",
  rate_per_ton: "rate_per_ton",
  source_document: "source_document",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyFeeRateFormDialogProps {
  trigger: ReactNode;
  initialData?: FeeRateDto;
  onSubmitted?: (rate: FeeRateDto) => void;
}

/**
 * Форма ставки платы за НВОС (разд. 55.3, срез-102).
 *
 * Четыре поля на первом уровне: год, вид воздействия, предмет платы и сама
 * ставка; реквизиты документа и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: ставку устанавливает Правительство и меняет ежегодно — платформа её
 * не знает и не подсказывает. Год, вид и предмет при правке заперты: ручка
 * PATCH их не принимает, а ставка на другой год — это другая ставка (и суммы
 * прошлых лет от такой «правки» поехали бы задним числом).
 */
export const EcologyFeeRateFormDialog = ({
  trigger,
  initialData,
  onSubmitted,
}: EcologyFeeRateFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyFeeRateFormValues>({
    resolver: zodResolver(ecologyFeeRateFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        year: String(initialData.year),
        impact_kind: initialData.impact_kind,
        subject: initialData.subject,
        rate_per_ton: initialData.rate_per_ton,
        source_document: initialData.source_document ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyFeeRateFormValues) => {
    const editable = {
      rate_per_ton: feeNumberToPayload(values.rate_per_ton),
      source_document: orNull(values.source_document),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateFeeRate(initialData.id, editable)
        : await ecologyApi.createFeeRate({
            year: Number(values.year),
            impact_kind: values.impact_kind,
            subject: values.subject.trim(),
            ...editable,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Ставка обновлена" : "Ставка внесена");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить ставку");
      } else {
        toast.error("Не удалось сохранить ставку");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyFeeRateFormValues) => {
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
            {isEdit ? "Изменить ставку" : "Внести ставку"}
          </DialogTitle>
          <DialogDescription>
            Ставку устанавливает Правительство и меняет ежегодно: платформа её
            не знает и не подсказывает. Исправленная ставка сразу меняет суммы
            всех строк своего года.
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
              <Label htmlFor="eco-rate-year">Год</Label>
              <Input
                id="eco-rate-year"
                type="number"
                min={2000}
                max={2100}
                inputMode="numeric"
                disabled={isEdit}
                {...form.register("year")}
              />
              {fieldError("year")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-rate-kind">Вид воздействия</Label>
              <select
                id="eco-rate-kind"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("impact_kind")}
              >
                {Object.entries(FEE_IMPACT_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("impact_kind")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-rate-subject">Предмет платы</Label>
              <Input
                id="eco-rate-subject"
                placeholder="напр. Азота диоксид"
                disabled={isEdit}
                {...form.register("subject")}
              />
              {fieldError("subject")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-rate-value">Ставка, ₽/т</Label>
              <Input
                id="eco-rate-value"
                inputMode="decimal"
                placeholder="из постановления"
                {...form.register("rate_per_ton")}
              />
              {fieldError("rate_per_ton")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Откуда взята ставка и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="eco-rate-source">Документ</Label>
                <Input
                  id="eco-rate-source"
                  placeholder="реквизиты постановления"
                  {...form.register("source_document")}
                />
                {fieldError("source_document")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="eco-rate-notes">Заметки</Label>
                <Textarea
                  id="eco-rate-notes"
                  rows={3}
                  placeholder="особенности применения"
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
