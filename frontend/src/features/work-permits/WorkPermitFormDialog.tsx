import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

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
import { workPermitsApi } from "@/api/workPermits";
import type { WorkPermitDto } from "@/types/dto/workPermits";
import {
  SAFETY_SYSTEM_CODES,
  workPermitSchema,
  type WorkPermitFormValues,
} from "@/types/forms/workPermits";
import { SAFETY_SYSTEM_LABELS, WORK_TYPE_LABELS } from "@/lib/workPermitVocab";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const EMPTY: WorkPermitFormValues = {
  work_type: "height",
  number: "",
  subdivision_text: "",
  site_id: "",
  zone_text: "",
  planned_start: "",
  planned_end: "",
  content_text: "",
  conditions_text: "",
  hazards_text: "",
  safety_systems: [],
  measures_before_text: "",
  measures_during_text: "",
  special_conditions_text: "",
  ppe_text: "",
};

interface Props {
  trigger: ReactNode;
  initialData?: WorkPermitDto;
  onSubmitted?: (wp: WorkPermitDto) => void;
}

const ta = "min-h-[64px] w-full rounded-md border px-3 py-2 text-sm";

export const WorkPermitFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const form = useForm<WorkPermitFormValues>({
    resolver: zodResolver(workPermitSchema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        work_type: initialData.work_type,
        number: initialData.number ?? "",
        subdivision_text: initialData.subdivision_text ?? "",
        site_id: initialData.site_id ?? "",
        zone_text: initialData.zone_text,
        planned_start: initialData.planned_start?.slice(0, 16) ?? "",
        planned_end: initialData.planned_end?.slice(0, 16) ?? "",
        content_text: initialData.content_text ?? "",
        conditions_text: initialData.conditions_text ?? "",
        hazards_text: initialData.hazards_text ?? "",
        safety_systems: (initialData.safety_systems ?? []) as WorkPermitFormValues["safety_systems"],
        measures_before_text: initialData.measures_before_text ?? "",
        measures_during_text: initialData.measures_during_text ?? "",
        special_conditions_text: initialData.special_conditions_text ?? "",
        ppe_text: initialData.ppe_text ?? "",
      });
    } else {
      form.reset(EMPTY);
    }
  }, [open, initialData, form]);

  const toBody = (v: WorkPermitFormValues): Record<string, unknown> => ({
    work_type: v.work_type,
    zone_text: v.zone_text,
    number: v.number || null,
    subdivision_text: v.subdivision_text || null,
    site_id: v.site_id || null,
    content_text: v.content_text || null,
    conditions_text: v.conditions_text || null,
    hazards_text: v.hazards_text || null,
    safety_systems: v.safety_systems && v.safety_systems.length ? v.safety_systems : null,
    measures_before_text: v.measures_before_text || null,
    measures_during_text: v.measures_during_text || null,
    special_conditions_text: v.special_conditions_text || null,
    ppe_text: v.ppe_text || null,
    planned_start: v.planned_start ? new Date(v.planned_start).toISOString() : null,
    planned_end: v.planned_end ? new Date(v.planned_end).toISOString() : null,
  });

  const onSubmit = async (v: WorkPermitFormValues) => {
    try {
      const result = initialData
        ? await workPermitsApi.update(initialData.id, toBody(v))
        : await workPermitsApi.create(toBody(v));
      onSubmitted?.(result);
      toast.success(initialData ? "Наряд обновлён" : "Наряд создан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) applyApiFieldErrorsToForm(form.setError, err, {});
      toast.error("Не удалось сохранить наряд");
    }
  };

  const selected = new Set(form.watch("safety_systems") ?? []);
  const toggleSystem = (code: (typeof SAFETY_SYSTEM_CODES)[number]) => {
    const next = new Set(selected);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("safety_systems", Array.from(next) as WorkPermitFormValues["safety_systems"]);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать наряд" : "Новый наряд-допуск"}</DialogTitle>
          <DialogDescription>Работа на высоте (форма 782н)</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast в onSubmit */
            }
          })}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="work_type">Вид работ</Label>
              <select
                id="work_type"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("work_type")}
              >
                {Object.entries(WORK_TYPE_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="number">Номер</Label>
              <Input id="number" {...form.register("number")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="subdivision_text">Подразделение</Label>
              <Input id="subdivision_text" {...form.register("subdivision_text")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="zone_text">Зона работ</Label>
              <Input id="zone_text" {...form.register("zone_text")} />
              {form.formState.errors.zone_text && (
                <p className="text-xs text-destructive">{form.formState.errors.zone_text.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="planned_start">Начало</Label>
              <Input id="planned_start" type="datetime-local" {...form.register("planned_start")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="planned_end">Окончание</Label>
              <Input id="planned_end" type="datetime-local" {...form.register("planned_end")} />
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="content_text">Содержание работ</Label>
            <textarea id="content_text" className={ta} {...form.register("content_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="conditions_text">Условия проведения</Label>
            <textarea id="conditions_text" className={ta} {...form.register("conditions_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="hazards_text">Опасные факторы</Label>
            <textarea id="hazards_text" className={ta} {...form.register("hazards_text")} />
          </div>

          <div className="space-y-1">
            <Label>Системы обеспечения безопасности</Label>
            <div className="flex flex-wrap gap-3">
              {SAFETY_SYSTEM_CODES.map((code) => (
                <label key={code} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selected.has(code)}
                    onChange={() => toggleSystem(code)}
                  />
                  {SAFETY_SYSTEM_LABELS[code]}
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="measures_before_text">Мероприятия до начала работ</Label>
            <textarea id="measures_before_text" className={ta} {...form.register("measures_before_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="measures_during_text">Мероприятия в процессе работ</Label>
            <textarea id="measures_during_text" className={ta} {...form.register("measures_during_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="special_conditions_text">Особые условия</Label>
            <textarea
              id="special_conditions_text"
              className={ta}
              {...form.register("special_conditions_text")}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ppe_text">Перечень СИЗ</Label>
            <textarea id="ppe_text" className={ta} {...form.register("ppe_text")} />
          </div>

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
