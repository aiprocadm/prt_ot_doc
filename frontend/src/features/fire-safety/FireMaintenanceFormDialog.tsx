import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FIRE_EQUIPMENT_TITLES,
  FIRE_MAINTENANCE_KIND_TITLES,
  FIRE_MAINTENANCE_RESULT_TITLES,
  fireSafetyApi,
  type FireEquipmentDto,
  type FireEquipmentKind,
  type FireMaintenanceDto,
} from "@/api/fireSafety";
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
  fireMaintenanceFormSchema,
  type FireMaintenanceFormValues,
} from "@/types/forms/fireSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: FireMaintenanceFormValues = {
  equipment_id: "",
  kind: "inspection",
  performed_on: "",
  result: "passed",
  performer: "",
  next_due: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof FireMaintenanceFormValues> = {
  equipment_id: "equipment_id",
  kind: "kind",
  performed_on: "performed_on",
  result: "result",
  performer: "performer",
  next_due: "next_due",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface FireMaintenanceFormDialogProps {
  trigger: ReactNode;
  equipment: FireEquipmentDto[];
  presetEquipmentId?: string;
  onSubmitted?: (record: FireMaintenanceDto) => void;
}

/**
 * Форма записи о регламентной работе по ПБ (разд. 54.1, срез-103).
 *
 * Четыре поля на первом уровне: средство, вид работы, дата и результат;
 * исполнитель, следующий срок и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: срок средства двигает СЕРВЕР и только по исправному результату —
 * «неисправно» срок не переносит, иначе просрочка исчезла бы с экрана, а
 * неисправность осталась. Записи только добавляются: у ручки нет правки —
 * запись о работе это свершившийся факт, а не черновик.
 */
export const FireMaintenanceFormDialog = ({
  trigger,
  equipment,
  presetEquipmentId,
  onSubmitted,
}: FireMaintenanceFormDialogProps) => {
  const [open, setOpen] = useState(false);

  const form = useForm<FireMaintenanceFormValues>({
    resolver: zodResolver(fireMaintenanceFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    form.reset({ ...emptyForm, equipment_id: presetEquipmentId ?? "" });
  }, [open, presetEquipmentId, form]);

  const onSubmit = async (values: FireMaintenanceFormValues) => {
    try {
      const result = await fireSafetyApi.recordMaintenance({
        equipment_id: values.equipment_id,
        kind: values.kind,
        performed_on: values.performed_on,
        result: values.result,
        performer: orNull(values.performer),
        next_due: orNull(values.next_due),
        notes: orNull(values.notes),
      });
      onSubmitted?.(result);
      toast.success("Работа записана");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось записать работу");
      } else {
        toast.error("Не удалось записать работу");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof FireMaintenanceFormValues) => {
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
          <DialogTitle>Записать работу</DialogTitle>
          <DialogDescription>
            Запись подтверждает исправность средства. Срок переносится системой
            и только по исправному результату: «неисправно» срок не двигает —
            иначе просрочка исчезла бы, а неисправность осталась.
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
            <Label htmlFor="fire-maint-unit">Средство</Label>
            <select
              id="fire-maint-unit"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("equipment_id")}
            >
              <option value="">— Выберите средство —</option>
              {equipment.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.label} ·{" "}
                  {FIRE_EQUIPMENT_TITLES[unit.kind as FireEquipmentKind] ??
                    unit.kind}
                </option>
              ))}
            </select>
            {fieldError("equipment_id")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="fire-maint-kind">Вид работы</Label>
              <select
                id="fire-maint-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(FIRE_MAINTENANCE_KIND_TITLES).map(
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
              <Label htmlFor="fire-maint-date">Дата работы</Label>
              <Input
                id="fire-maint-date"
                type="date"
                {...form.register("performed_on")}
              />
              {fieldError("performed_on")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="fire-maint-result">Результат</Label>
            <select
              id="fire-maint-result"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("result")}
            >
              {Object.entries(FIRE_MAINTENANCE_RESULT_TITLES).map(
                ([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ),
              )}
            </select>
            {fieldError("result")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Исполнитель, следующий срок и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fire-maint-performer">Исполнитель</Label>
                  <Input
                    id="fire-maint-performer"
                    placeholder="организация или работник"
                    {...form.register("performer")}
                  />
                  {fieldError("performer")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fire-maint-next">Следующий срок</Label>
                  <Input
                    id="fire-maint-next"
                    type="date"
                    title="Пусто — срок перенесёт система по результату"
                    {...form.register("next_due")}
                  />
                  {fieldError("next_due")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="fire-maint-notes">Заметки</Label>
                <Textarea
                  id="fire-maint-notes"
                  rows={3}
                  placeholder="номер акта, выявленные замечания"
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
