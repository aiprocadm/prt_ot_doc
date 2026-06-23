import { useEffect, useState, type ChangeEvent, type ReactNode } from "react";
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
  GAS_PARAMETER_CODES,
  VENTILATION_CODES,
  FIRE_FIGHTING_MEANS_CODES,
  RESPIRATORY_PPE_CODES,
  ELECTRICAL_MEASURE_CODES,
  VOLTAGE_CONDITION_CODES,
  UTILITY_CODES,
  SHORING_METHOD_CODES,
  workPermitSchema,
  type WorkPermitFormValues,
} from "@/types/forms/workPermits";
import {
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  LEGAL_REFERENCE_LABELS,
  GAS_PARAMETER_LABELS,
  VENTILATION_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
  RESPIRATORY_PPE_LABELS,
  ELECTRICAL_MEASURES_LABELS,
  VOLTAGE_CONDITION_LABELS,
  UTILITIES_LABELS,
  SHORING_METHOD_LABELS,
} from "@/lib/workPermitVocab";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";
import { GasAnalysisEditor, type GasRow } from "@/features/work-permits/GasAnalysisEditor";

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
  type_specific: null,
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
        type_specific: (initialData.type_specific as WorkPermitFormValues["type_specific"]) ?? null,
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
    type_specific: ["confined_space", "hot_work", "gas_hazardous", "electrical", "excavation"].includes(v.work_type)
      ? (v.type_specific ?? null)
      : null,
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

  // Структурные данные у видов работ не совпадают: type_specific (confined/hot/gas) и
  // height-специфичный чеклист safety_systems. При смене вида сбрасываем оба, иначе чужие
  // ключи/данные предыдущего вида уйдут на сервер (напр. safety_systems высоты на газоопасном
  // наряде). Сброс срабатывает только при действии пользователя — первичная загрузка черновика
  // идёт через form.reset в useEffect выше.
  const workTypeReg = form.register("work_type");
  const onWorkTypeChange = (e: ChangeEvent<HTMLSelectElement>) => {
    void workTypeReg.onChange(e);
    form.setValue("type_specific", null);
    form.setValue("safety_systems", []);
  };

  // Снимки для `checked`-пропсов считаются на рендере (через watch — подписка на ререндер).
  // Сами тоггл-хендлеры читают АКТУАЛЬНОЕ состояние формы через getValues, а не render-снимок:
  // иначе два быстрых клика до ререндера видели бы один устаревший снимок и второй перетёр бы первый.
  const selected = new Set(form.watch("safety_systems") ?? []);
  const toggleSystem = (code: (typeof SAFETY_SYSTEM_CODES)[number]) => {
    const next = new Set(form.getValues("safety_systems") ?? []);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("safety_systems", Array.from(next) as WorkPermitFormValues["safety_systems"]);
  };

  // Один хендлер для всех type_specific-массивов (огневые/газоопасные/электро).
  // Читает актуальный стор через getValues — два быстрых клика до ререндера не теряют друг друга.
  const toggleTsCode = (
    field: "fire_fighting_means" | "respiratory_ppe" | "technical_measures" | "utilities",
    code: string,
  ) => {
    const current = (form.getValues("type_specific") ?? {}) as Record<string, string[] | undefined>;
    const next = new Set(current[field] ?? []);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("type_specific", {
      ...current,
      [field]: Array.from(next),
    } as WorkPermitFormValues["type_specific"]);
  };

  const selectedMeans = new Set(
    ((form.watch("type_specific") as { fire_fighting_means?: string[] } | null)?.fire_fighting_means) ?? [],
  );
  const selectedResp = new Set(
    ((form.watch("type_specific") as { respiratory_ppe?: string[] } | null)?.respiratory_ppe) ?? [],
  );
  const selectedMeasures = new Set(
    ((form.watch("type_specific") as { technical_measures?: string[] } | null)?.technical_measures) ?? [],
  );
  const selectedUtilities = new Set(
    ((form.watch("type_specific") as { utilities?: string[] } | null)?.utilities) ?? [],
  );

  // Редактор замеров (общий для ОЗП/огневых/газоопасных). Мутации через getValues — без stale-snapshot.
  const updateGas = (mut: (rows: GasRow[]) => GasRow[]) => {
    const current = (form.getValues("type_specific") ?? {}) as { gas_analysis?: GasRow[] };
    const rows = mut([...(current.gas_analysis ?? [])]);
    form.setValue("type_specific", {
      ...current,
      gas_analysis: rows,
    } as WorkPermitFormValues["type_specific"]);
  };
  const gasRows =
    ((form.watch("type_specific") as { gas_analysis?: GasRow[] } | null)?.gas_analysis) ?? [];
  const gasEditorProps = {
    rows: gasRows,
    onAdd: () => updateGas((r) => [...r, { parameter: "oxygen", value: "" }]),
    onRemove: (i: number) => updateGas((r) => r.filter((_, j) => j !== i)),
    onCell: (i: number, f: keyof GasRow, v: string) =>
      updateGas((r) =>
        r.map((row, j) => (j === i ? { ...row, [f]: f === "value" ? v : v || undefined } : row)),
      ),
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать наряд" : "Новый наряд-допуск"}</DialogTitle>
          <DialogDescription>
            {WORK_TYPE_LABELS[form.watch("work_type")] ?? "Наряд-допуск"} ·{" "}
            {LEGAL_REFERENCE_LABELS[form.watch("work_type")] ?? ""}
          </DialogDescription>
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
                {...workTypeReg}
                onChange={onWorkTypeChange}
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

          {form.watch("work_type") === "height" && (
            <div className="space-y-1">
              <Label>Системы обеспечения безопасности</Label>
              <div className="flex flex-wrap gap-3">
                {SAFETY_SYSTEM_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={selected.has(code)} onChange={() => toggleSystem(code)} />
                    {SAFETY_SYSTEM_LABELS[code]}
                  </label>
                ))}
              </div>
            </div>
          )}

          {form.watch("work_type") === "confined_space" && (
            <div className="space-y-2">
              <Label>Анализ воздушной среды и вентиляция (902н)</Label>
              <div className="space-y-1">
                <Label htmlFor="ventilation" className="text-xs">Вентиляция</Label>
                <select
                  id="ventilation"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.ventilation as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      ventilation: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {VENTILATION_CODES.map((c) => (
                    <option key={c} value={c}>{VENTILATION_LABELS[c]}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Изоляция коммуникаций и средства эвакуации — в полях «Мероприятия» / «Особые условия».
              </p>
              <GasAnalysisEditor {...gasEditorProps} />
            </div>
          )}

          {form.watch("work_type") === "hot_work" && (
            <div className="space-y-2">
              <Label>Пожарная безопасность огневых работ (1479)</Label>
              <Label className="text-xs">Средства пожаротушения</Label>
              <div className="flex flex-wrap gap-3">
                {FIRE_FIGHTING_MEANS_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedMeans.has(code)}
                      onChange={() => toggleTsCode("fire_fighting_means", code)}
                    />
                    {FIRE_FIGHTING_MEANS_LABELS[code]}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров концентрации: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Подготовка/очистка места и контроль после работ — в полях «Мероприятия» / «Особые условия».
              </p>
              <GasAnalysisEditor {...gasEditorProps} />
            </div>
          )}

          {form.watch("work_type") === "gas_hazardous" && (
            <div className="space-y-2">
              <Label>Защита органов дыхания и анализ среды (528)</Label>
              <Label className="text-xs">СИЗ органов дыхания (СИЗОД)</Label>
              <div className="flex flex-wrap gap-3">
                {RESPIRATORY_PPE_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedResp.has(code)}
                      onChange={() => toggleTsCode("respiratory_ppe", code)}
                    />
                    {RESPIRATORY_PPE_LABELS[code]}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров концентрации: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Продувка/вентиляция и контроль среды — в полях «Мероприятия» / «Особые условия».
              </p>
              <GasAnalysisEditor {...gasEditorProps} />
            </div>
          )}

          {form.watch("work_type") === "electrical" && (
            <div className="space-y-2">
              <Label>Меры безопасности в электроустановках (903н)</Label>
              <Label className="text-xs">Технические мероприятия подготовки места</Label>
              <div className="flex flex-wrap gap-3">
                {ELECTRICAL_MEASURE_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedMeasures.has(code)}
                      onChange={() => toggleTsCode("technical_measures", code)}
                    />
                    {ELECTRICAL_MEASURES_LABELS[code]}
                  </label>
                ))}
              </div>
              <div className="space-y-1">
                <Label htmlFor="voltage_condition" className="text-xs">Условие проведения</Label>
                <select
                  id="voltage_condition"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.voltage_condition as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      voltage_condition: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {VOLTAGE_CONDITION_CODES.map((c) => (
                    <option key={c} value={c}>{VOLTAGE_CONDITION_LABELS[c]}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {form.watch("work_type") === "excavation" && (
            <div className="space-y-2">
              <Label>Безопасность земляных работ (883н)</Label>
              <Label className="text-xs">Подземные коммуникации в зоне работ</Label>
              <div className="flex flex-wrap gap-3">
                {UTILITY_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedUtilities.has(code)}
                      onChange={() => toggleTsCode("utilities", code)}
                    />
                    {UTILITIES_LABELS[code]}
                  </label>
                ))}
              </div>
              <div className="space-y-1">
                <Label htmlFor="shoring" className="text-xs">Защита стенок выемки</Label>
                <select
                  id="shoring"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.shoring as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      shoring: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {SHORING_METHOD_CODES.map((c) => (
                    <option key={c} value={c}>{SHORING_METHOD_LABELS[c]}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

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
