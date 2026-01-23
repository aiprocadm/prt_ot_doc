import { useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRiskStore } from "@/stores/risk";
import { useCompaniesStore } from "@/stores/companies";
import { riskAssessmentSchema, type RiskAssessmentFormValues } from "@/types/forms/risk";

export const RiskAssessmentForm = () => {
  const { hazards, listHazards, createAssessment } = useRiskStore();
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const form = useForm<RiskAssessmentFormValues>({
    resolver: zodResolver(riskAssessmentSchema),
    defaultValues: { company_id: "", hazards: [] }
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "hazards" });

  useEffect(() => {
    listHazards();
    listCompanies();
  }, [listCompanies, listHazards]);

  const handleAddHazard = (hazardId: string) => {
    if (!hazardId) return;
    append({ hazard_id: hazardId, probability: 1, severity: 1, mitigations: "" });
  };

  const onSubmit = async (values: RiskAssessmentFormValues) => {
    await createAssessment(values);
    toast.success("Расчёт сохранён");
    form.reset({ company_id: "", hazards: [] });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">Новый расчёт риска</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="space-y-2">
            <Label htmlFor="risk-company">Компания</Label>
            <select id="risk-company" className="h-10 rounded-md border px-3" {...form.register("company_id")}>
              <option value="">—</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Добавить опасность</Label>
            <div className="flex gap-2">
              <select className="h-10 flex-1 rounded-md border px-3" onChange={(event) => handleAddHazard(event.target.value)}>
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
              <div key={field.id} className="grid gap-2 rounded-md border p-3 md:grid-cols-4">
                <div className="md:col-span-2">
                  <Label className="text-xs uppercase text-muted-foreground">Опасность</Label>
                  <div className="text-sm font-medium">
                    {hazards.find((hazard) => hazard.id === field.hazard_id)?.title ?? field.hazard_id}
                  </div>
                </div>
                <div>
                  <Label htmlFor={`probability-${index}`}>Вероятность</Label>
                  <Input
                    id={`probability-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    {...form.register(`hazards.${index}.probability`, { valueAsNumber: true })}
                  />
                </div>
                <div>
                  <Label htmlFor={`severity-${index}`}>Тяжесть</Label>
                  <Input
                    id={`severity-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    {...form.register(`hazards.${index}.severity`, { valueAsNumber: true })}
                  />
                </div>
                <div className="md:col-span-4">
                  <Label htmlFor={`mitigations-${index}`}>Мероприятия</Label>
                  <Input id={`mitigations-${index}`} {...form.register(`hazards.${index}.mitigations`)} />
                </div>
                <div className="md:col-span-4">
                  <Button variant="outline" type="button" onClick={() => remove(index)}>
                    Удалить
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Сохранение..." : "Сохранить расчёт"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
};
