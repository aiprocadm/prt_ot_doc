import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FEE_IMPACT_KIND_TITLES,
  ecologyApi,
  type FeeLineDto,
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
  ecologyFeeLineFormSchema,
  feeNumberToPayload,
  type EcologyFeeLineFormValues,
} from "@/types/forms/ecologyFee";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const QUARTER_TITLES: Record<string, string> = {
  "1": "I квартал",
  "2": "II квартал",
  "3": "III квартал",
  "4": "IV квартал",
};

const emptyForm: EcologyFeeLineFormValues = {
  year: String(new Date().getFullYear()),
  quarter: "1",
  impact_kind: "emission",
  subject: "",
  mass_tons: "",
  coefficient: "1",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyFeeLineFormValues> = {
  year: "year",
  quarter: "quarter",
  impact_kind: "impact_kind",
  subject: "subject",
  mass_tons: "mass_tons",
  coefficient: "coefficient",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyFeeLineFormDialogProps {
  trigger: ReactNode;
  initialData?: FeeLineDto;
  onSubmitted?: (line: FeeLineDto) => void;
}

/**
 * Форма строки расчёта платы за НВОС (разд. 55.3, срез-102).
 *
 * Шесть полей на первом уровне: год, квартал, вид воздействия, предмет платы,
 * масса и коэффициент; заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: сумму считает сервер, перемножая массу, ставку своего года и
 * коэффициент, — форма ничего не подсчитывает и не показывает «примерную»
 * сумму. Если ставки за год нет, сумма не считается ВООБЩЕ (не ноль): «ноль»
 * читался бы как «платить нечего». Ключ строки (год, квартал, вид, предмет)
 * при правке заперт — ручка PATCH его не принимает.
 */
export const EcologyFeeLineFormDialog = ({
  trigger,
  initialData,
  onSubmitted,
}: EcologyFeeLineFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyFeeLineFormValues>({
    resolver: zodResolver(ecologyFeeLineFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        year: String(initialData.year),
        quarter: String(initialData.quarter),
        impact_kind: initialData.impact_kind,
        subject: initialData.subject,
        mass_tons: initialData.mass_tons,
        coefficient: initialData.coefficient,
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyFeeLineFormValues) => {
    const editable = {
      mass_tons: feeNumberToPayload(values.mass_tons),
      coefficient: feeNumberToPayload(values.coefficient),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateFeeLine(initialData.id, editable)
        : await ecologyApi.createFeeLine({
            year: Number(values.year),
            quarter: Number(values.quarter),
            impact_kind: values.impact_kind,
            subject: values.subject.trim(),
            ...editable,
          });
      onSubmitted?.(result);
      toast.success(isEdit ? "Строка обновлена" : "Строка расчёта внесена");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить строку расчёта");
      } else {
        toast.error("Не удалось сохранить строку расчёта");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyFeeLineFormValues) => {
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
            {isEdit ? "Изменить строку расчёта" : "Внести строку расчёта"}
          </DialogTitle>
          <DialogDescription>
            Сумму считает система: масса × ставка своего года × коэффициент.
            Если ставки за год нет, сумма не считается вовсе — это не ноль.
            Коэффициент 1 означает «без повышающего».
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
              <Label htmlFor="eco-line-year">Год</Label>
              <Input
                id="eco-line-year"
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
              <Label htmlFor="eco-line-quarter">Квартал</Label>
              {/* Квартал — он же авансовый платёж: за него платят отдельно. */}
              <select
                id="eco-line-quarter"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={isEdit}
                {...form.register("quarter")}
              >
                {Object.entries(QUARTER_TITLES).map(([value, title]) => (
                  <option key={value} value={value}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("quarter")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-line-kind">Вид воздействия</Label>
              <select
                id="eco-line-kind"
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
            <div className="space-y-2">
              <Label htmlFor="eco-line-subject">Предмет платы</Label>
              <Input
                id="eco-line-subject"
                placeholder="напр. Азота диоксид"
                disabled={isEdit}
                {...form.register("subject")}
              />
              {fieldError("subject")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-line-mass">Масса, т</Label>
              <Input
                id="eco-line-mass"
                inputMode="decimal"
                placeholder="за квартал"
                {...form.register("mass_tons")}
              />
              {fieldError("mass_tons")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-line-coefficient">Коэффициент</Label>
              <Input
                id="eco-line-coefficient"
                inputMode="decimal"
                title="1 — без повышающего коэффициента"
                {...form.register("coefficient")}
              />
              {fieldError("coefficient")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Заметки
            </summary>
            <div className="mt-3 space-y-2">
              <Label htmlFor="eco-line-notes">Заметки</Label>
              <Textarea
                id="eco-line-notes"
                rows={3}
                placeholder="основание коэффициента, особенности расчёта"
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
