import { useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useRiskStore } from "@/stores/risk";
import { useCompaniesStore } from "@/stores/companies";
import {
  riskAssessmentSchema,
  type RiskAssessmentFormValues,
} from "@/types/forms/risk";

export const RiskAssessmentForm = () => {
  const { hazards, createAssessment } = useRiskStore();
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const { can } = useAbility();
  const canAssess = can(PERMISSIONS.RISK_ASSESS);
  const form = useForm<RiskAssessmentFormValues>({
    resolver: zodResolver(riskAssessmentSchema),
    defaultValues: { company_id: "", hazards: [] },
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "hazards",
  });

  useEffect(() => {
    if (canAssess) {
      void listCompanies();
    }
  }, [canAssess, listCompanies]);

  const handleAddHazard = (hazardId: string) => {
    if (!hazardId) return;
    append({
      hazard_id: hazardId,
      probability: 1,
      severity: 1,
    });
  };

  const scoreHint = (probability?: number, severity?: number) => {
    const p = Number(probability ?? 0);
    const s = Number(severity ?? 0);
    const score = p * s;
    if (!score) return "—";
    if (score >= 15) return `${score} (критический)`;
    if (score >= 10) return `${score} (высокий)`;
    if (score >= 6) return `${score} (средний)`;
    return `${score} (низкий)`;
  };

  const onSubmit = async (values: RiskAssessmentFormValues) => {
    try {
      await createAssessment(values);
      toast.success("Расчёт сохранён");
      form.reset({ company_id: "", hazards: [] });
    } catch (error) {
      toast.error((error as Error)?.message ?? "Не удалось сохранить расчёт");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">
          Новый расчёт риска
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!canAssess && (
          <div className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Только просмотр
          </div>
        )}
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="space-y-2">
            <Label htmlFor="risk-company">Компания</Label>
            <select
              id="risk-company"
              className="h-10 rounded-md border px-3"
              disabled={!canAssess}
              {...form.register("company_id")}
            >
              <option value="">—</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="risk-hazard">Добавить опасность</Label>
            <div className="flex gap-2">
              <select
                id="risk-hazard"
                className="h-10 flex-1 rounded-md border px-3"
                disabled={!canAssess}
                onChange={(event) => handleAddHazard(event.target.value)}
              >
                <option value="">Выберите опасность</option>
                {hazards.map((hazard) => (
                  <option key={hazard.id} value={hazard.id}>
                    {hazard.title}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-3">
            {fields.map((field, index) => (
              <div
                key={field.id}
                className="grid gap-2 rounded-md border p-3 md:grid-cols-4"
              >
                <div className="md:col-span-2">
                  <Label className="text-xs uppercase text-muted-foreground">
                    Опасность
                  </Label>
                  <div className="text-sm font-medium">
                    {hazards.find((hazard) => hazard.id === field.hazard_id)
                      ?.title ?? field.hazard_id}
                  </div>
                </div>
                <div>
                  <Label htmlFor={`probability-${index}`}>Вероятность</Label>
                  <Input
                    id={`probability-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    disabled={!canAssess}
                    {...form.register(`hazards.${index}.probability`, {
                      valueAsNumber: true,
                    })}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Шкала 1-5
                  </p>
                </div>
                <div>
                  <Label htmlFor={`severity-${index}`}>Тяжесть</Label>
                  <Input
                    id={`severity-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    disabled={!canAssess}
                    {...form.register(`hazards.${index}.severity`, {
                      valueAsNumber: true,
                    })}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Шкала 1-5
                  </p>
                </div>
                <div className="md:col-span-4 text-xs text-muted-foreground">
                  Индекс по опасности:{" "}
                  {scoreHint(
                    form.watch(`hazards.${index}.probability`),
                    form.watch(`hazards.${index}.severity`),
                  )}
                </div>
                <div className="md:col-span-4">
                  <Button
                    variant="outline"
                    type="button"
                    disabled={!canAssess}
                    onClick={() => remove(index)}
                  >
                    Удалить
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <Button
            type="submit"
            disabled={!canAssess || form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? "Сохранение..." : "Сохранить расчёт"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
};
