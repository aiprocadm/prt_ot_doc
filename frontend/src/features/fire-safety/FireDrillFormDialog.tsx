import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  FIRE_DRILL_KIND_TITLES,
  FIRE_DRILL_OUTCOME_TITLES,
  fireSafetyApi,
  type FireDrillDto,
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
  fireDrillFormSchema,
  participantsToPayload,
  type FireDrillFormValues,
} from "@/types/forms/fireSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: FireDrillFormValues = {
  kind: "evacuation",
  title: "",
  planned_on: "",
  site_id: "",
  held_on: "",
  outcome: "",
  participants: "",
  scenario: "",
  findings: "",
};

const API_FIELD_MAP: Record<string, keyof FireDrillFormValues> = {
  kind: "kind",
  title: "title",
  planned_on: "planned_on",
  site_id: "site_id",
  held_on: "held_on",
  outcome: "outcome",
  participants: "participants",
  scenario: "scenario",
  findings: "findings",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface FireDrillFormDialogProps {
  trigger: ReactNode;
  sites: Site[];
  initialData?: FireDrillDto;
  onSubmitted?: (drill: FireDrillDto) => void;
}

/**
 * Форма тренировки или учения по ПБ (разд. 54.1, срез-104).
 *
 * Четыре поля на первом уровне: вид, название, дата по плану и площадка.
 * Протокол проведения — дата, результат, участники, сценарий и анализ — под
 * «Дополнительно» (ТЗ разд. 59.3): тренировку сначала планируют, а протокол
 * появляется позже, и держать его в основной форме значит требовать данных,
 * которых ещё нет.
 *
 * ГРАНИЦЫ: протокол обязан быть цельным — проведена → есть результат,
 * результат → есть дата проведения (оба правила стоят и на сервере, форма
 * показывает их до запроса). Интервал «не реже раза в полгода» платформа не
 * судит: он относится к объектам с массовым пребыванием людей, а признака
 * массового пребывания в данных нет.
 */
export const FireDrillFormDialog = ({
  trigger,
  sites,
  initialData,
  onSubmitted,
}: FireDrillFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<FireDrillFormValues>({
    resolver: zodResolver(fireDrillFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        kind: initialData.kind,
        title: initialData.title,
        planned_on: initialData.planned_on,
        site_id: initialData.site_id ?? "",
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

  const onSubmit = async (values: FireDrillFormValues) => {
    const body = {
      kind: values.kind,
      title: values.title.trim(),
      planned_on: values.planned_on,
      site_id: orNull(values.site_id),
      held_on: orNull(values.held_on),
      outcome: orNull(values.outcome),
      participants: participantsToPayload(values.participants),
      scenario: orNull(values.scenario),
      findings: orNull(values.findings),
    };
    try {
      const result = initialData
        ? await fireSafetyApi.updateDrill(initialData.id, body)
        : await fireSafetyApi.createDrill(body);
      onSubmitted?.(result);
      toast.success(
        isEdit ? "Тренировка обновлена" : "Тренировка запланирована",
      );
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить тренировку");
      } else {
        toast.error("Не удалось сохранить тренировку");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof FireDrillFormValues) => {
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
            {isEdit ? "Изменить тренировку" : "Запланировать тренировку"}
          </DialogTitle>
          <DialogDescription>
            Тренировка заводится по плану, протокол вносится после проведения:
            дата и результат идут только вместе. Периодичность определяет
            специалист — платформа её не назначает.
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
              <Label htmlFor="fire-drill-kind">Вид</Label>
              <select
                id="fire-drill-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(FIRE_DRILL_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="fire-drill-planned">По плану</Label>
              <Input
                id="fire-drill-planned"
                type="date"
                {...form.register("planned_on")}
              />
              {fieldError("planned_on")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="fire-drill-title">Тренировка</Label>
            <Input
              id="fire-drill-title"
              placeholder="напр. Эвакуация административного корпуса"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="space-y-2">
            <Label htmlFor="fire-drill-site">Площадка</Label>
            <select
              id="fire-drill-site"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("site_id")}
            >
              <option value="">— Не привязана —</option>
              {sites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </select>
            {fieldError("site_id")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Протокол проведения: дата, результат, участники, анализ
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fire-drill-held">Проведена</Label>
                  <Input
                    id="fire-drill-held"
                    type="date"
                    title="Дата в будущем — это план, а не протокол"
                    {...form.register("held_on")}
                  />
                  {fieldError("held_on")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fire-drill-outcome">Результат</Label>
                  <select
                    id="fire-drill-outcome"
                    className="h-10 w-full rounded-md border px-3"
                    {...form.register("outcome")}
                  >
                    <option value="">— Не проведена —</option>
                    {Object.entries(FIRE_DRILL_OUTCOME_TITLES).map(
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
                <Label htmlFor="fire-drill-participants">Участников</Label>
                <Input
                  id="fire-drill-participants"
                  type="number"
                  min={0}
                  inputMode="numeric"
                  title="Пусто — сведения не внесены, а не «ноль человек»"
                  {...form.register("participants")}
                />
                {fieldError("participants")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="fire-drill-scenario">Сценарий</Label>
                <Textarea
                  id="fire-drill-scenario"
                  rows={3}
                  placeholder="вводная, отрабатываемые действия"
                  {...form.register("scenario")}
                />
                {fieldError("scenario")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="fire-drill-findings">Анализ и замечания</Label>
                <Textarea
                  id="fire-drill-findings"
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
