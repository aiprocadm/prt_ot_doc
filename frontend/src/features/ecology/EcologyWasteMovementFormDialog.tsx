import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  WASTE_MOVEMENT_KIND_TITLES,
  ecologyApi,
  type WasteMovementDto,
  type WastePassportDto,
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
  ecologyWasteMovementFormSchema,
  massToPayload,
  type EcologyWasteMovementFormValues,
} from "@/types/forms/ecologyWasteMovement";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: EcologyWasteMovementFormValues = {
  passport_id: "",
  kind: "generated",
  happened_on: "",
  quantity_tons: "",
  counterparty: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof EcologyWasteMovementFormValues> = {
  passport_id: "passport_id",
  kind: "kind",
  happened_on: "happened_on",
  quantity_tons: "quantity_tons",
  counterparty: "counterparty",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface EcologyWasteMovementFormDialogProps {
  trigger: ReactNode;
  passports: WastePassportDto[];
  initialData?: WasteMovementDto;
  onSubmitted?: (movement: WasteMovementDto) => void;
}

/**
 * Форма записи журнала учёта отходов (разд. 55.2, срез-100).
 *
 * Пять полей на первом уровне: паспорт, вид движения, дата, масса и
 * контрагент; заметки — под «Дополнительно» (ТЗ разд. 59.3).
 *
 * ГРАНИЦА: договор с оператором выбрать пока нельзя — ядровой справочник
 * договоров на экран экологии не выведен, а вводить его id руками хуже, чем
 * не иметь поля вовсе. Контрагента вносят строкой, как и раньше через API.
 */
export const EcologyWasteMovementFormDialog = ({
  trigger,
  passports,
  initialData,
  onSubmitted,
}: EcologyWasteMovementFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<EcologyWasteMovementFormValues>({
    resolver: zodResolver(ecologyWasteMovementFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        passport_id: initialData.passport_id,
        kind: initialData.kind,
        happened_on: initialData.happened_on,
        quantity_tons: initialData.quantity_tons,
        counterparty: initialData.counterparty ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: EcologyWasteMovementFormValues) => {
    const body = {
      passport_id: values.passport_id,
      kind: values.kind,
      happened_on: values.happened_on,
      quantity_tons: massToPayload(values.quantity_tons),
      counterparty: orNull(values.counterparty),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await ecologyApi.updateWasteMovement(initialData.id, body)
        : await ecologyApi.createWasteMovement(body);
      onSubmitted?.(result);
      toast.success(isEdit ? "Запись обновлена" : "Движение записано");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить движение");
      } else {
        toast.error("Не удалось сохранить движение");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof EcologyWasteMovementFormValues) => {
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
            {isEdit ? "Изменить запись журнала" : "Записать движение"}
          </DialogTitle>
          <DialogDescription>
            Журнал фиксирует свершившееся: дата в будущем не принимается, а
            масса всегда больше нуля. Договор с оператором вносится в ядровом
            реестре договоров — здесь достаточно назвать контрагента.
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
            <Label htmlFor="eco-movement-passport">Паспорт отхода</Label>
            <select
              id="eco-movement-passport"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("passport_id")}
            >
              <option value="">— Выберите паспорт —</option>
              {passports.map((passport) => (
                <option key={passport.id} value={passport.id}>
                  {passport.name} · {passport.fkko_code}
                </option>
              ))}
            </select>
            {fieldError("passport_id")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-movement-kind">Движение</Label>
              <select
                id="eco-movement-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(WASTE_MOVEMENT_KIND_TITLES).map(
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
              <Label htmlFor="eco-movement-date">Дата</Label>
              <Input
                id="eco-movement-date"
                type="date"
                {...form.register("happened_on")}
              />
              {fieldError("happened_on")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="eco-movement-mass">Масса, т</Label>
              <Input
                id="eco-movement-mass"
                inputMode="decimal"
                placeholder="напр. 1,250"
                {...form.register("quantity_tons")}
              />
              {fieldError("quantity_tons")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="eco-movement-counterparty">Контрагент</Label>
              <Input
                id="eco-movement-counterparty"
                placeholder="оператор по обращению с отходами"
                {...form.register("counterparty")}
              />
              {fieldError("counterparty")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дополнительно
            </summary>
            <div className="mt-3 space-y-2">
              <Label htmlFor="eco-movement-notes">Заметки</Label>
              <Textarea
                id="eco-movement-notes"
                rows={3}
                placeholder="номер акта приёма-передачи, особенности"
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
