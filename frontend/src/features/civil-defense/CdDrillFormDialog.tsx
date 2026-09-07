import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  CD_DRILL_KIND_TITLES,
  CD_DRILL_OUTCOME_TITLES,
  civilDefenseApi,
  type DrillDto,
  type FormationDto,
} from "@/api/civilDefense";
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
  cdDrillFormSchema,
  cdParticipantsToPayload,
  type CdDrillFormValues,
} from "@/types/forms/civilDefense";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: CdDrillFormValues = {
  kind: "facility_training",
  title: "",
  planned_on: "",
  formation_id: "",
  held_on: "",
  outcome: "",
  participants: "",
  scenario: "",
  findings: "",
};

const API_FIELD_MAP: Record<string, keyof CdDrillFormValues> = {
  kind: "kind",
  title: "title",
  planned_on: "planned_on",
  formation_id: "formation_id",
  held_on: "held_on",
  outcome: "outcome",
  participants: "participants",
  scenario: "scenario",
  findings: "findings",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface CdDrillFormDialogProps {
  trigger: ReactNode;
  formations: FormationDto[];
  initialData?: DrillDto;
  onSubmitted?: (drill: DrillDto) => void;
}

/**
 * Форма учения или тренировки ГО (разд. 56.1, срез-109).
 *
 * Четыре поля на первом уровне: вид, название, дата по плану и формирование;
 * протокол — дата проведения, результат, участники, сценарий и анализ — под
 * «Дополнительно» (тот же приём, что у тренировок ПБ в срезе-104: учение
 * сначала планируют, протокол появляется позже).
 *
 * ГРАНИЦЫ: протокол обязан быть цельным — проведено → есть результат,
 * результат → есть дата (оба правила стоят и на сервере). Периодичность
 * учений платформа не назначает: она следует из категории организации по ГО.
 * Формирование необязательно — учение бывает общеобъектовым.
 */
export const CdDrillFormDialog = ({
  trigger,
  formations,
  initialData,
  onSubmitted,
}: CdDrillFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<CdDrillFormValues>({
    resolver: zodResolver(cdDrillFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        title: initialData.title,
        planned_on: initialData.planned_on,
        formation_id: initialData.formation_id ?? "",
        held_on: initialData.held_on ?? "",
        outcome: initialData.outcome ?? "",
        participants:
          initialData.participants != null
            ? String(initialData.participants)
            : "",
        scenario: initialData.scenario ?? "",
        findings: initialData.findings ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: CdDrillFormValues) => {
    const common = {
      kind: values.kind,
      title: values.title.trim(),
      planned_on: values.planned_on,
      formation_id: orNull(values.formation_id),
      participants: cdParticipantsToPayload(values.participants),
      scenario: orNull(values.scenario),
    };
    try {
      const result = initialData
        ? await civilDefenseApi.updateDrill(initialData.id, {
            ...common,
            held_on: orNull(values.held_on),
            outcome: orNull(values.outcome),
            findings: orNull(values.findings),
          })
        : await civilDefenseApi.createDrill(common);
      onSubmitted?.(result);
      toast.success(isEdit ? "Учение обновлено" : "Учение запланировано");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить учение");
      } else {
        toast.error("Не удалось сохранить учение");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof CdDrillFormValues) => {
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
            {isEdit ? "Изменить учение" : "Запланировать учение"}
          </DialogTitle>
          <DialogDescription>
            Учение заводится по плану, протокол вносится после проведения: дата
            и результат идут только вместе. Периодичность следует из категории
            организации по ГО — платформа её не назначает.
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
              <Label htmlFor="cd-drill-kind">Вид</Label>
              <select
                id="cd-drill-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(CD_DRILL_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-drill-planned">По плану</Label>
              <Input
                id="cd-drill-planned"
                type="date"
                {...form.register("planned_on")}
              />
              {fieldError("planned_on")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cd-drill-title">Учение</Label>
            <Input
              id="cd-drill-title"
              placeholder="напр. Тренировка по эвакуации при угрозе ЧС"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cd-drill-formation">Формирование</Label>
            <select
              id="cd-drill-formation"
              className="h-10 w-full rounded-md border px-3"
              title="Пусто — учение общеобъектовое"
              {...form.register("formation_id")}
            >
              <option value="">— Общеобъектовое —</option>
              {formations.map((formation) => (
                <option key={formation.id} value={formation.id}>
                  {formation.name}
                </option>
              ))}
            </select>
            {fieldError("formation_id")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Протокол проведения: дата, результат, участники, анализ
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cd-drill-held">Проведено</Label>
                  <Input
                    id="cd-drill-held"
                    type="date"
                    title="Дата в будущем — это план, а не протокол"
                    {...form.register("held_on")}
                  />
                  {fieldError("held_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cd-drill-outcome">Результат</Label>
                  <select
                    id="cd-drill-outcome"
                    className="h-10 w-full rounded-md border px-3"
                    {...form.register("outcome")}
                  >
                    <option value="">— Не проведено —</option>
                    {Object.entries(CD_DRILL_OUTCOME_TITLES).map(
                      ([code, title]) => (
                        <option key={code} value={code}>
                          {title}
                        </option>
                      ),
                    )}
                  </select>
                  {fieldError("outcome")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-drill-participants">Участников</Label>
                <Input
                  id="cd-drill-participants"
                  type="number"
                  min={0}
                  inputMode="numeric"
                  title="Пусто — сведения не внесены, а не «ноль человек»"
                  {...form.register("participants")}
                />
                {fieldError("participants")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-drill-scenario">Сценарий</Label>
                <Textarea
                  id="cd-drill-scenario"
                  rows={3}
                  placeholder="вводная, отрабатываемые действия"
                  {...form.register("scenario")}
                />
                {fieldError("scenario")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-drill-findings">Анализ и замечания</Label>
                <Textarea
                  id="cd-drill-findings"
                  rows={3}
                  placeholder="что пошло не так, какие меры приняты"
                  {...form.register("findings")}
                />
                {fieldError("findings")}
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
